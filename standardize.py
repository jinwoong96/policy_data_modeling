### 4) 값 표준화 - 지역 / 날짜 / 신청·사업기간 / 재직상태 등을 표준값으로 통일
# standardize.py

import csv
import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 지역 표준화
# ---------------------------------------------------------------------------

def load_zip_mapping(path: str) -> Dict[str, str]:
    """
    시군구코드 -> "시도 시군구" 이름 매핑을 로드한다.
    """
    mapping = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["시군구코드"].strip()
            name = row["지역명"].strip()
            mapping[code] = name
    return mapping


def _build_province_index(zip_mapping: Dict[str, str]) -> Dict[str, List[str]]:
    """
    "시도" -> 그 시도에 속한 전체 "시도 시군구" 이름 리스트.
    특정 정책이 한 시도의 모든 시군구를 커버하는지 판단할 때 쓴다.
    """
    index: Dict[str, List[str]] = {}
    for name in zip_mapping.values():
        province = name.split(" ")[0]
        index.setdefault(province, []).append(name)
    return index


class RegionStandardizer:
    def __init__(self, zip_mapping_path: str):
        self.zip_mapping = load_zip_mapping(zip_mapping_path)
        self.province_index = _build_province_index(self.zip_mapping)
        self.total_district_count = len(self.zip_mapping)

    def from_ontong_zipcd(self, zip_cd: str) -> List[str]:
        """
        온통청년의 zipCd(쉼표로 구분된 시군구코드 목록)를 표준 지역명 리스트로 변환.
        - 전체 시군구의 95% 이상을 커버하면 ["전국"]으로 축약
        - 한 시도의 시군구를 전부 커버하면 "{시도} 전체"로 축약
        - 그 외에는 "{시도} {시군구}" 이름을 그대로 나열
        """
        codes = [c.strip() for c in (zip_cd or "").split(",") if c.strip()]
        if not codes:
            return []

        if len(codes) >= self.total_district_count * 0.95:
            return ["전국"]

        names = [self.zip_mapping.get(c) for c in codes]
        names = [n for n in names if n]

        by_province: Dict[str, List[str]] = {}
        for name in names:
            province = name.split(" ")[0]
            by_province.setdefault(province, []).append(name)

        result: List[str] = []
        for province, province_names in by_province.items():
            full_list = self.province_index.get(province, [])
            if full_list and set(province_names) >= set(full_list):
                result.append(f"{province} 전체")
            else:
                result.extend(sorted(set(province_names)))

        return result

    def from_welfare_ctpv_sgg(self, ctpv_nm: str, sgg_nm: str) -> List[str]:
        """
        지자체복지서비스의 ctpvNm(시도명) + sggNm(시군구명)을 표준 지역명으로 변환.
        """
        ctpv_nm = (ctpv_nm or "").strip()
        sgg_nm = (sgg_nm or "").strip()

        if not ctpv_nm:
            return []

        if sgg_nm:
            return [f"{ctpv_nm} {sgg_nm}"]

        return [f"{ctpv_nm} 전체"]


# ---------------------------------------------------------------------------
# 날짜 / 기간 표준화
# ---------------------------------------------------------------------------

INDEFINITE_END_DATES = {"99991231", "9999-12-31"}


def format_ymd(ymd: Optional[str]) -> Optional[str]:
    """
    "YYYYMMDD" -> "YYYY-MM-DD". 형식이 아니면 None.
    """
    if not ymd:
        return None

    ymd = ymd.strip()
    if not re.match(r"^\d{8}$", ymd):
        return None

    return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"


# 온통청년 신청기간구분코드(aplyPrdSeCd) 매핑 (데이터 실측으로 확인)
ONTONG_APLY_PRD_SE_CD_MAP = {
    "0057001": "특정기간",
    "0057002": "상시",
    "0057003": "마감",
}

# 온통청년 사업기간구분코드(bizPrdSeCd) 매핑 (데이터 실측으로 확인)
ONTONG_BIZ_PRD_SE_CD_MAP = {
    "0056001": "기간한정",
    "0056002": "상시",
}


def ontong_apply_period(record: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """
    온통청년 레코드의 "신청기간" (aplyPrdSeCd/aplyYmd 기반).
    """
    code = record.get("aplyPrdSeCd", "")
    period_type = ONTONG_APLY_PRD_SE_CD_MAP.get(code, "확인필요")

    if period_type != "특정기간":
        return period_type, None

    aply_ymd = (record.get("aplyYmd") or "").strip()
    match = re.match(r"(\d{8})\s*~\s*(\d{8})", aply_ymd)
    if not match:
        return period_type, aply_ymd or None

    start_raw, end_raw = match.groups()
    return period_type, f"{format_ymd(start_raw)} ~ {format_ymd(end_raw)}"


def ontong_service_period(record: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """
    온통청년 레코드의 "사업(시행)기간" (bizPrdSeCd/bizPrdBgngYmd/EndYmd 기반).
    """
    code = record.get("bizPrdSeCd", "")
    period_type = ONTONG_BIZ_PRD_SE_CD_MAP.get(code, "확인필요")

    if period_type != "기간한정":
        return period_type, None

    start = format_ymd(record.get("bizPrdBgngYmd"))
    end = format_ymd(record.get("bizPrdEndYmd"))

    if start and end:
        return period_type, f"{start} ~ {end}"

    return period_type, None


def welfare_service_period(record: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """
    지자체복지서비스 레코드의 "사업(시행)기간" (enfcBgngYmd/enfcEndYmd 기반).
    이 API에는 온통청년의 aplyPrdSeCd 같은 "신청기간" 개념 자체가 없어서,
    신청기간은 항상 "확인필요"로 남기고 여기서는 시행기간만 표준화한다.
    """
    end_raw = (record.get("enfcEndYmd") or "").strip()

    if end_raw in INDEFINITE_END_DATES or not end_raw:
        return "상시", None

    start = format_ymd(record.get("enfcBgngYmd"))
    end = format_ymd(end_raw)

    if start and end:
        return "기간한정", f"{start} ~ {end}"

    return "확인필요", None


def clean_ontong_age(min_age_raw: str, max_age_raw: str):
    """
    온통청년 sprtTrgtMinAge/MaxAge 원문 값을 정제한다.
    데이터에 "하한은 있는데 상한이 0" 이거나 "999세" 같은 더미/오류성 값이
    소수 섞여 있어서(실측 확인: 2633건 중 14건), 그런 경우 상한을 None으로 비운다.
    """
    min_age = int(min_age_raw) if str(min_age_raw).isdigit() else None
    max_age = int(max_age_raw) if str(max_age_raw).isdigit() else None

    if max_age is not None and (max_age == 0 or max_age > 100):
        max_age = None
    if min_age is not None and min_age == 0 and max_age is None:
        min_age = None

    return min_age, max_age


# ---------------------------------------------------------------------------
# 재직/취업 상태 표준화 (자유 텍스트 -> 표준 태그)
# ---------------------------------------------------------------------------

# (표준 태그, 텍스트에서 찾을 키워드들)
EMPLOYMENT_STATUS_RULES: List[Tuple[str, List[str]]] = [
    ("미취업자", ["미취업", "구직자", "구직 중", "무직"]),
    ("재직자", ["재직자", "재직 중", "근로자", "직장인"]),
    ("자영업자", ["자영업자", "소상공인", "1인 창업자", "개인사업자"]),
    ("창업자", ["예비창업자", "창업자", "창업 준비"]),
    ("재학생", ["재학생", "휴학생", "대학생", "대학원생"]),
    ("졸업생", ["졸업생", "졸업예정자", "미취업 졸업생"]),
    ("농업인", ["농업인", "귀농", "농업 종사자"]),
    ("프리랜서", ["프리랜서", "특수형태근로종사자", "예술인"]),
]


def extract_employment_status(*texts: Optional[str]) -> List[str]:
    """
    여러 자유 텍스트를 훑어서 표준 재직/취업 상태 태그를 뽑는다.
    같은 텍스트 안에 여러 상태가 언급되면 전부 반환(중복 제거, 순서 유지).
    """
    joined = " ".join(t for t in texts if t)
    if not joined:
        return []

    found: List[str] = []
    for tag, keywords in EMPLOYMENT_STATUS_RULES:
        if any(kw in joined for kw in keywords):
            if tag not in found:
                found.append(tag)

    return found
