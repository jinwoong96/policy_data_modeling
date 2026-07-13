### 3) 필드 매핑 어댑터 - 각 출처 레코드를 공통 스키마로 변환
# adapters.py

from typing import Any, Dict, Optional

from condition_extract import extract_age_range, extract_income_condition
from schema import new_common_record
from standardize import (
    ONTONG_JOB_CD_MAP,
    ONTONG_MAJOR_CD_MAP,
    ONTONG_MRG_STTS_CD_MAP,
    ONTONG_PLCY_PVSN_MTHD_CD_MAP,
    ONTONG_SBIZ_CD_MAP,
    ONTONG_SCHOOL_CD_MAP,
    RegionStandardizer,
    clean_ontong_age,
    decode_multi_code,
    decode_single_code,
    extract_employment_status,
    format_ymd,
    ontong_apply_period,
    ontong_service_period,
    welfare_service_period,
)


def _parse_int(value: Optional[str]) -> Optional[int]:
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def _normalize_link(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    # "www.xxx.kr" 처럼 스킴이 빠진 원본 데이터가 종종 있어서 보정한다.
    return f"https://{value}"


def _pick_ontong_link(record: Dict[str, Any]) -> str:
    for field in ("aplyUrlAddr", "refUrlAddr1", "refUrlAddr2"):
        value = (record.get(field) or "").strip()
        if value:
            return _normalize_link(value)
    return ""


def _pick_welfare_link(record: Dict[str, Any]) -> str:
    """
    inqplHmpgReldList는 dict(항목 1개) 또는 list(항목 여러 개)로 들어온다.
    그 안에서 URL처럼 생긴 wlfareInfoReldCn 값을 첫 번째로 찾아서 반환.
    """
    value = record.get("inqplHmpgReldList")
    if not value:
        return ""

    items = value if isinstance(value, list) else [value]
    for item in items:
        if not isinstance(item, dict):
            continue
        cn = (item.get("wlfareInfoReldCn") or "").strip()
        if cn.startswith("http") or cn.startswith("www."):
            return _normalize_link(cn)
    return ""


def _ontong_income_condition(record: Dict[str, Any]) -> Optional[str]:
    """
    소득조건구분코드(earnCndSeCd)를 먼저 보고, 코드가 알려주는 의미에 맞게 처리한다
    (실측 확인: 0043001=무관 2277건 - earnEtcCn 항상 비어있음 / 0043002=연소득 29건 -
    earnEtcCn은 항상 비어있고 대신 earnMinAmt/earnMaxAmt(만원 단위)에 실제 금액이 들어있음 /
    0043003=기타 325건 - earnEtcCn에 조건 원문이 들어있음).
    코드만 보고는 "연소득"인데 금액이 비어 있는 극소수 사례가 있어서, 그런 경우엔
    earnEtcCn 기반 추출로 폴백한다.
    """
    code = (record.get("earnCndSeCd") or "").strip()
    earn_etc = (record.get("earnEtcCn") or "").strip()
    earn_min = _parse_int(record.get("earnMinAmt")) or None
    earn_max = _parse_int(record.get("earnMaxAmt")) or None
    # 금액이 비정상적으로 커 보이는 경우(예: 4,300억원)도 있지만, 온통청년 공식
    # 사이트 게시물에도 원본 그대로 노출되는 값이라 임의로 걸러내지 않고 원본을 그대로 쓴다.

    if code == "0043001":  # 무관 - 소득 조건 없음
        return None

    if code == "0043002":  # 연소득 - 구조화된 금액 우선 사용
        if earn_min and earn_max:
            return f"연소득 {earn_min:,}만원 ~ {earn_max:,}만원"
        if earn_max:
            return f"연소득 {earn_max:,}만원 이하"
        if earn_min:
            return f"연소득 {earn_min:,}만원 이상"
        # 금액이 비어있는 예외 케이스 - 텍스트로 폴백
        return extract_income_condition(earn_etc) or (earn_etc or None)

    # "0043003"(기타) 또는 코드가 비어있는 경우 - 기존 방식대로 자유텍스트에서 추출
    return extract_income_condition(earn_etc) or (earn_etc or None)


def _ontong_target_text(record: Dict[str, Any]) -> str:
    parts = []

    age_limit_yn = (record.get("sprtTrgtAgeLmtYn") or "").strip()
    min_age, max_age = clean_ontong_age(
        record.get("sprtTrgtMinAge") or "", record.get("sprtTrgtMaxAge") or ""
    )

    if age_limit_yn == "Y" and (min_age or max_age):
        if min_age and max_age:
            parts.append(f"만 {min_age}~{max_age}세")
        elif min_age:
            parts.append(f"만 {min_age}세 이상")
        elif max_age:
            parts.append(f"만 {max_age}세 이하")

    earn_etc = (record.get("earnEtcCn") or "").strip()
    if earn_etc:
        parts.append(earn_etc)

    add_qlfc = (record.get("addAplyQlfcCndCn") or "").strip()
    if add_qlfc:
        parts.append(add_qlfc)

    return " | ".join(parts) if parts else ""


def ontong_to_common(record: Dict[str, Any], region_std: RegionStandardizer) -> dict:
    apply_period_type, apply_period = ontong_apply_period(record)
    service_period_type, service_period = ontong_service_period(record)

    age_limit_yn = (record.get("sprtTrgtAgeLmtYn") or "").strip()
    target_age_min, target_age_max = clean_ontong_age(
        record.get("sprtTrgtMinAge") or "", record.get("sprtTrgtMaxAge") or ""
    )
    if age_limit_yn != "Y":
        target_age_min = target_age_max = None

    income_condition = _ontong_income_condition(record)

    keywords = []
    for field in ("plcyKywdNm", "lclsfNm", "mclsfNm"):
        value = (record.get(field) or "").strip()
        if value:
            keywords.extend([k.strip() for k in value.split(",") if k.strip()])

    target_text = _ontong_target_text(record)
    support_text = (record.get("plcySprtCn") or "").strip()

    # employment_status: jobCd(구조화된 코드, 신뢰도 높음)를 기본으로 쓰고,
    # 자유 텍스트 스캔 결과를 더해서 놓치는 게 없게 한다(합집합, 중복 제거).
    # 주의: ptcpPrpTrgtCn(참여제한대상내용)은 "제외 대상"을 적은 필드라서
    # 긍정 스캔에 같이 넣으면 안 됨 (예: "졸업생 제외"에서 "졸업생"을 지원대상으로 잘못 태깅).
    employment_status = list(dict.fromkeys(
        decode_multi_code(record.get("jobCd"), ONTONG_JOB_CD_MAP)
        + extract_employment_status(record.get("addAplyQlfcCndCn"))
    ))

    provision_method_label = decode_single_code(record.get("plcyPvsnMthdCd"), ONTONG_PLCY_PVSN_MTHD_CD_MAP)
    provision_method = [provision_method_label] if provision_method_label else []

    return new_common_record(
        source="ontong",
        source_id=record.get("plcyNo", ""),
        title=record.get("plcyNm", ""),
        agency=(record.get("sprvsnInstCdNm") or record.get("operInstCdNm") or "").strip(),
        region_names=region_std.from_ontong_zipcd(record.get("zipCd", "")),
        life_cycle=["청년"],
        theme_keywords=keywords,
        employment_status=employment_status,
        apply_period_type=apply_period_type,
        apply_period=apply_period,
        service_period_type=service_period_type,
        service_period=service_period,
        target_text=target_text,
        target_age_min=target_age_min,
        target_age_max=target_age_max,
        target_income_condition=income_condition,
        support_text=support_text,
        apply_method=(record.get("plcyAplyMthdCn") or "").strip(),
        link=_pick_ontong_link(record),
        description=(record.get("plcyExplnCn") or "").strip(),
        provision_method=provision_method,
        special_target_groups=decode_multi_code(record.get("sbizCd"), ONTONG_SBIZ_CD_MAP),
        education_condition=decode_multi_code(record.get("schoolCd"), ONTONG_SCHOOL_CD_MAP),
        major_condition=decode_multi_code(record.get("plcyMajorCd"), ONTONG_MAJOR_CD_MAP),
        marital_status=decode_single_code(record.get("mrgSttsCd"), ONTONG_MRG_STTS_CD_MAP),
        view_count=_parse_int(record.get("inqCnt")),
        last_updated=(record.get("lastMdfcnDt") or "").strip().split(" ")[0] or None,
        raw=record,
    )


def welfare_to_common(record: Dict[str, Any], region_std: RegionStandardizer) -> dict:
    service_period_type, service_period = welfare_service_period(record)

    target_text_parts = []
    sprt_trgt = (record.get("sprtTrgtCn") or "").strip()
    slct_crit = (record.get("slctCritCn") or "").strip()
    if sprt_trgt:
        target_text_parts.append(sprt_trgt)
    if slct_crit and slct_crit != sprt_trgt:
        target_text_parts.append(slct_crit)
    target_text = " | ".join(target_text_parts)

    age_min, age_max = extract_age_range(target_text)
    income_condition = extract_income_condition(target_text)

    life_cycle_raw = (record.get("lifeNmArray") or "").strip()
    life_cycle = [v.strip() for v in life_cycle_raw.split(",") if v.strip()]

    theme_raw = (record.get("intrsThemaNmArray") or "").strip()
    theme_keywords = [v.strip() for v in theme_raw.split(",") if v.strip()]

    employment_status = extract_employment_status(sprt_trgt, slct_crit)

    apply_method = (record.get("aplyMtdNm") or record.get("aplyMtdCn") or "").strip()

    provision_method_raw = (record.get("srvPvsnNm") or "").strip()
    provision_method = [v.strip() for v in provision_method_raw.split(",") if v.strip()]

    special_target_raw = (record.get("trgterIndvdlNmArray") or "").strip()
    special_target_groups = [v.strip() for v in special_target_raw.split(",") if v.strip()]

    return new_common_record(
        source="welfare",
        source_id=record.get("servId", ""),
        title=record.get("servNm", ""),
        agency=(record.get("bizChrDeptNm") or "").strip(),
        region_names=region_std.from_welfare_ctpv_sgg(record.get("ctpvNm", ""), record.get("sggNm", "")),
        life_cycle=life_cycle,
        theme_keywords=theme_keywords,
        employment_status=employment_status,
        apply_period_type="확인필요",  # 이 API에는 신청기간 개념 자체가 없음
        apply_period=None,
        service_period_type=service_period_type,
        service_period=service_period,
        target_text=target_text,
        target_age_min=age_min,
        target_age_max=age_max,
        target_income_condition=income_condition,
        support_text=(record.get("alwServCn") or "").strip(),
        apply_method=apply_method,
        link=_pick_welfare_link(record),
        description=(record.get("servDgst") or "").strip(),
        provision_method=provision_method,
        special_target_groups=special_target_groups,
        education_condition=[],  # 이 API에는 학력 조건 개념이 없음
        major_condition=[],  # 이 API에는 전공계열 조건 개념이 없음
        marital_status=None,  # 이 API에는 혼인상태 조건 개념이 없음
        view_count=_parse_int(record.get("inqNum")),
        last_updated=format_ymd(record.get("lastModYmd")),
        raw=record,
    )
