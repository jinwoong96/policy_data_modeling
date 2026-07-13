### 3) 필드 매핑 - 두 출처를 온통청년 스키마(ontong_schema.py) 기준으로 통합
# adapters.py
#
# [브랜치 변경] 온통청년 레코드는 원본 그대로 통과시키고, 지자체복지서비스 레코드만
# 온통청년 필드에 맞춰 변환한다. 지자체 API에 대응 개념이 아예 없는 "구조화된 코드"
# 필드(jobCd/schoolCd/mrgSttsCd/sbizCd/plcyMajorCd/plcyPvsnMthdCd/aplyPrdSeCd/
# bizPrdSeCd 등)는 근거 없이 코드를 지어내지 않고 빈 문자열로 남긴다 - 예전에
# ptcpPrpTrgtCn을 잘못 해석해서 태그를 잘못 붙였던 사례를 감안해, "모르면 비워둔다"를
# 원칙으로 삼는다. 대신 텍스트로나마 남길 수 있는 정보(제공방식명, 대상군 텍스트 등)는
# etcMttrCn / addAplyQlfcCndCn 같은 온통청년의 자유 텍스트 필드에 보존해서 유실을 막는다.

from typing import Any, Dict, Optional

from condition_extract import extract_age_range, extract_income_condition
from ontong_schema import new_ontong_record
from standardize import RegionStandardizer, format_ymd, INDEFINITE_END_DATES


def ontong_passthrough(record: Dict[str, Any]) -> dict:
    """
    온통청년 레코드는 필드명/코드값을 그대로 유지한다 (변형 없음).
    """
    return new_ontong_record(source="ontong", raw=None, **record)


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
            return cn if cn.startswith("http") else f"https://{cn}"
    return ""


def _welfare_target_text(record: Dict[str, Any]) -> str:
    sprt_trgt = (record.get("sprtTrgtCn") or "").strip()
    slct_crit = (record.get("slctCritCn") or "").strip()
    if sprt_trgt and slct_crit and slct_crit != sprt_trgt:
        return f"{sprt_trgt} | {slct_crit}"
    return sprt_trgt or slct_crit


def _welfare_biz_period(record: Dict[str, Any]):
    """
    지자체복지서비스의 enfcBgngYmd/enfcEndYmd(시행기간)를 온통청년의
    bizPrdBgngYmd/bizPrdEndYmd/bizPrdEtcCn 형태로 옮긴다.
    bizPrdSeCd(사업기간구분코드)는 지어내지 않고 빈 값으로 둔다 - 대신
    bizPrdEtcCn에 "상시" 여부만 텍스트로 남겨서 정보를 보존한다.
    """
    bgng = (record.get("enfcBgngYmd") or "").strip()
    end = (record.get("enfcEndYmd") or "").strip()

    if end in INDEFINITE_END_DATES or not end:
        return bgng, "", "상시"

    return bgng, end, ""


# 지자체복지서비스 API의 "관심주제"(intrsThemaNmArray)는 자유텍스트가 아니라 공식 코드표
# (지자체복지서비스_코드표(v1.0).doc, 관심주제 14종: 신체건강/정신건강/생활지원/주거/일자리/
# 문화·여가/안전·위기/임신·출산/보육/교육/입양·위탁/보호·돌봄/서민금융/법률)에 정의된
# 고정 값이라, 온통청년 대분류(lclsfNm, 5종: 일자리/주거/교육/복지문화/참여권리)로의 매핑도
# 코드표 대 코드표 대응이라 "지어내는" 것과는 다르다고 보고 채운다.
# 반면 mclsfNm(중분류)은 두 코드표 사이에 이 정도로 명확한 대응이 없어 계속 비워둔다.
WELFARE_THEME_TO_LCLSF = {
    "일자리": "일자리",
    "주거": "주거",
    "교육": "교육",
    "법률": "참여권리",
    "안전·위기": "참여권리",
    "신체건강": "복지문화",
    "정신건강": "복지문화",
    "생활지원": "복지문화",
    "문화·여가": "복지문화",
    "임신·출산": "복지문화",
    "보육": "복지문화",
    "입양·위탁": "복지문화",
    "보호·돌봄": "복지문화",
    "서민금융": "복지문화",
}
# 한 레코드에 관심주제가 여러 개 걸려 있을 때(예: "일자리, 서민금융") 어느 대분류를
# 대표값으로 쓸지 우선순위. 일자리/주거/교육처럼 구체적인 분류를 "복지문화"라는
# 포괄 분류보다 우선한다.
WELFARE_LCLSF_PRIORITY = ["일자리", "주거", "교육", "참여권리", "복지문화"]


def _welfare_lclsf(theme_text: str) -> str:
    themes = [t.strip() for t in (theme_text or "").split(",") if t.strip()]
    buckets = {WELFARE_THEME_TO_LCLSF[t] for t in themes if t in WELFARE_THEME_TO_LCLSF}
    for candidate in WELFARE_LCLSF_PRIORITY:
        if candidate in buckets:
            return candidate
    return ""


def welfare_to_ontong(record: Dict[str, Any], region_std: RegionStandardizer) -> dict:
    target_text = _welfare_target_text(record)
    age_min, age_max = extract_age_range(target_text)
    income_condition = extract_income_condition(target_text)

    biz_bgng, biz_end, biz_etc = _welfare_biz_period(record)

    apply_method_parts = [
        (record.get("aplyMtdNm") or "").strip(),
        (record.get("aplyMtdCn") or "").strip(),
    ]
    apply_method = " / ".join(p for p in apply_method_parts if p)

    # 제공방식(srvPvsnNm)은 온통청년의 plcyPvsnMthdCd(코드)에 대응되지만, 코드를
    # 추측해서 넣지 않고 원문 텍스트를 etcMttrCn에 남긴다.
    provision_text = (record.get("srvPvsnNm") or "").strip()
    special_target_text = (record.get("trgterIndvdlNmArray") or "").strip()
    etc_parts = []
    if provision_text:
        etc_parts.append(f"[제공방식] {provision_text}")
    if special_target_text:
        etc_parts.append(f"[가구상황] {special_target_text}")
    etc_mttr_cn = " ".join(etc_parts)

    zip_cd = region_std.to_ontong_zipcd(record.get("ctpvNm", ""), record.get("sggNm", ""))

    return new_ontong_record(
        source="welfare",
        raw=record,

        plcyNo=record.get("servId", ""),
        plcyNm=record.get("servNm", ""),
        plcyKywdNm=(record.get("intrsThemaNmArray") or "").strip(),
        plcyExplnCn=(record.get("servDgst") or "").strip(),
        # lclsfNm: 관심주제(intrsThemaNmArray) 코드표를 온통청년 대분류로 매핑 (위 설명 참고)
        lclsfNm=_welfare_lclsf(record.get("intrsThemaNmArray")),
        # mclsfNm: 온통청년 자체 중분류 체계와 명확히 대응되지 않아 비움
        # plcyPvsnMthdCd: 코드 대응 불확실 - 비움 (원문은 etcMttrCn에 보존)

        # pvsnInstGroupCd: 지자체복지서비스 출처 자체가 "지자체"이므로 이건 추측이 아니라
        # 출처 정보 그 자체 - 온통청년 코드표 기준 0054002(지자체)를 채운다.
        pvsnInstGroupCd="0054002",
        sprvsnInstCdNm=(record.get("bizChrDeptNm") or "").strip(),

        sprtTrgtAgeLmtYn="Y" if (age_min is not None or age_max is not None) else "N",
        sprtTrgtMinAge=str(age_min) if age_min is not None else "",
        sprtTrgtMaxAge=str(age_max) if age_max is not None else "",

        # mrgSttsCd/earnCndSeCd/earnMinAmt/earnMaxAmt: 구조화된 코드/금액 대응 없음 - 비움
        earnEtcCn=income_condition or "",

        addAplyQlfcCndCn=(record.get("slctCritCn") or "").strip(),
        # ptcpPrpTrgtCn: 지자체 API엔 "참여제한대상" 개념 자체가 없음 - 비움
        # jobCd/schoolCd/plcyMajorCd/sbizCd: 구조화된 코드 대응 없음 - 비움 (추측 금지)

        # aplyPrdSeCd/aplyYmd: 지자체 API엔 "신청기간" 개념 자체가 없음(사업 시행기간만 있음) - 비움
        bizPrdBgngYmd=biz_bgng,
        bizPrdEndYmd=biz_end,
        bizPrdEtcCn=biz_etc,

        plcySprtCn=(record.get("alwServCn") or "").strip(),
        # sprtSclCnt/sprtSclLmtYn/sprtArvlSeqYn: 지원규모/선착순 개념 없음 - 비움

        plcyAplyMthdCn=apply_method,
        # srngMthdCn/sbmsnDcmntCn: 심사방법/제출서류 개념 없음 - 비움

        aplyUrlAddr=_pick_welfare_link(record),
        # refUrlAddr1/2: 부가링크 없음 - 비움

        zipCd=zip_cd,

        # rgtrInstCd 등 등록기관 체계, plcyAprvSttsCd(온통청년 내부 승인상태),
        # frstRegDt(최초등록일 개념 없음, lastModYmd만 있음), bscPlan* (내부 계획연계
        # 코드): 전부 대응 없음 - 비움

        lastMdfcnDt=format_ymd(record.get("lastModYmd")) or "",
        inqCnt=(record.get("inqNum") or "").strip(),

        etcMttrCn=etc_mttr_cn,
    )
