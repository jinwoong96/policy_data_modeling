### 3) 필드 매핑 어댑터 - 각 출처 레코드를 공통 스키마로 변환
# adapters.py

from typing import Any, Dict

from condition_extract import extract_age_range, extract_income_condition
from schema import new_common_record
from standardize import (
    RegionStandardizer,
    clean_ontong_age,
    extract_employment_status,
    ontong_apply_period,
    ontong_service_period,
    welfare_service_period,
)


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

    earn_etc = (record.get("earnEtcCn") or "").strip()
    income_condition = extract_income_condition(earn_etc) or (earn_etc or None)

    keywords = []
    for field in ("plcyKywdNm", "lclsfNm", "mclsfNm"):
        value = (record.get(field) or "").strip()
        if value:
            keywords.extend([k.strip() for k in value.split(",") if k.strip()])

    target_text = _ontong_target_text(record)
    support_text = (record.get("plcySprtCn") or "").strip()

    employment_status = extract_employment_status(
        record.get("addAplyQlfcCndCn"),
        record.get("ptcpPrpTrgtCn"),
    )

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
        raw=record,
    )
