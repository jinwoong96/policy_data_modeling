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

    # 지자체복지서비스 ctpvNm/sggNm에는 있지만 zipcd_mapping.csv(시군구코드 코드표)에는
    # 옛 지명으로 남아 있는 경우를 위한 별칭 - 실측으로 확인된 것만 등록한다.
    # (2025년 인천 중구 -> 제물포구 개편: 코드표는 아직 "중구"로 되어 있음)
    _REGION_NAME_ALIASES = {
        "인천광역시 제물포구": "인천광역시 중구",
    }

    def to_ontong_zipcd(self, ctpv_nm: str, sgg_nm: str) -> str:
        """
        지자체복지서비스의 ctpvNm(시도명) + sggNm(시군구명)을 온통청년 zipCd 형식
        (시군구코드를 콤마로 나열한 문자열)으로 역변환한다.

        - "시도 시군구" 이름이 zipcd_mapping.csv에 정확히 있으면 그 코드 하나.
        - 없으면(예: "경기도 수원시"처럼 시가 구 단위로 더 세분화된 경우) 그 이름으로
          시작하는 모든 시군구코드를 모아서 반환(예: 수원시 장안구/권선구/... 전부).
        - 알려진 개명 사례는 별칭 테이블로 보정한다.
        - sggNm이 비어 있으면(광역 단위 정책) 그 시도에 속한 모든 시군구코드를 반환한다.
        - 어느 쪽으로도 매칭이 안 되면 빈 문자열(= 확인 불가, 코드를 지어내지 않음).
        """
        ctpv_nm = (ctpv_nm or "").strip()
        sgg_nm = (sgg_nm or "").strip()
        if not ctpv_nm:
            return ""

        if not sgg_nm:
            codes = [code for code, name in self.zip_mapping.items() if name.split(" ")[0] == ctpv_nm]
            return ",".join(sorted(codes))

        full_name = f"{ctpv_nm} {sgg_nm}"
        full_name = self._REGION_NAME_ALIASES.get(full_name, full_name)

        name_to_codes: Dict[str, List[str]] = {}
        for code, name in self.zip_mapping.items():
            name_to_codes.setdefault(name, []).append(code)

        if full_name in name_to_codes:
            return ",".join(sorted(name_to_codes[full_name]))

        # 정확히 일치하는 이름이 없으면(대도시가 구 단위로 더 쪼개진 경우) 접두어로 모은다.
        prefix_codes = [
            code for name, codes in name_to_codes.items() if name.startswith(full_name)
            for code in codes
        ]
        if prefix_codes:
            return ",".join(sorted(prefix_codes))

        return ""


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

# 온통청년 사업기간구분코드(bizPrdSeCd) 매핑
# 공식 코드표(api_code_table/온통청년API코드정보.xlsx) 기준: 0056001=특정기간, 0056002=기타
# "기타"(0056002)를 곧바로 "상시"로 단정하면 안 된다 - 실측 결과 bizPrdEtcCn 자유텍스트에
# "연중"/"상시"/"계속"뿐 아니라 "2026. 1. ~ 12."처럼 실제 기간이 문장으로 들어있는
# 경우도 섞여 있었다(1035건 중 대략 170건). 그래서 텍스트를 다시 살펴서 분류한다.
ONTONG_BIZ_PRD_SE_CD_MAP = {
    "0056001": "기간한정",
    "0056002": "확인필요",  # 아래 ontong_service_period에서 bizPrdEtcCn을 보고 재분류함
}

_ONGOING_ETC_KEYWORDS = ["상시", "연중", "계속", "연례반복", "매년", "예산 소진"]
_YEAR_IN_ETC_PAT = re.compile(r"20\d{2}")


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

    if period_type == "기간한정":
        start = format_ymd(record.get("bizPrdBgngYmd"))
        end = format_ymd(record.get("bizPrdEndYmd"))
        if start and end:
            return period_type, f"{start} ~ {end}"
        return period_type, None

    if code == "0056002":
        # 공식 코드표상 "기타" - bizPrdEtcCn 자유 텍스트로 다시 분류
        etc = (record.get("bizPrdEtcCn") or "").strip()
        if not etc:
            return "확인필요", None
        if any(kw in etc for kw in _ONGOING_ETC_KEYWORDS) and not _YEAR_IN_ETC_PAT.search(etc):
            return "상시", None
        if _YEAR_IN_ETC_PAT.search(etc):
            # "2026. 1. ~ 12." 처럼 실제 기간이 문장으로 들어있는 경우: 형식이 제각각이라
            # YYYY-MM-DD로 못 바꾸고, 원문 그대로 보존한다.
            return "기간한정", etc
        return "확인필요", etc

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
# 온통청년 코드표 (api_code_table/온통청년API코드정보.xlsx 기준, 실측 확인)
# ---------------------------------------------------------------------------

# 정책제공방법코드(plcyPvsnMthdCd, 0042) - 값 1개
ONTONG_PLCY_PVSN_MTHD_CD_MAP = {
    "0042001": "인프라 구축",
    "0042002": "프로그램",
    "0042003": "직접대출",
    "0042004": "공공기관",
    "0042005": "계약(위탁운영)",
    "0042006": "보조금",
    "0042007": "대출보증",
    "0042008": "공적보험",
    "0042009": "조세지출",
    "0042010": "바우처",
    "0042011": "정보제공",
    "0042012": "경제적 규제",
    "0042013": "기타",
}

# 결혼상태코드(mrgSttsCd, 0055) - 값 1개
ONTONG_MRG_STTS_CD_MAP = {
    "0055001": "기혼",
    "0055002": "미혼",
    "0055003": "제한없음",
}

# 정책취업요건코드(jobCd, 0013) - 콤마로 여러 개 올 수 있음 (실측: 115건)
ONTONG_JOB_CD_MAP = {
    "0013001": "재직자",
    "0013002": "자영업자",
    "0013003": "미취업자",
    "0013004": "프리랜서",
    "0013005": "일용근로자",
    "0013006": "창업자",  # 원문 라벨은 "(예비)창업자" - 재직/취업 상태 표준 태그와 맞춰서 축약
    "0013007": "단기근로자",
    "0013008": "농업인",  # 원문 라벨은 "영농종사자" - 재직/취업 상태 표준 태그(농업인)와 통일
    "0013009": "기타",
    "0013010": "제한없음",
}

# 정책학력요건코드(schoolCd, 0049) - 콤마로 여러 개 올 수 있음 (실측: 149건)
ONTONG_SCHOOL_CD_MAP = {
    "0049001": "고졸 미만",
    "0049002": "고교 재학",
    "0049003": "고졸 예정",
    "0049004": "고교 졸업",
    "0049005": "대학 재학",
    "0049006": "대졸 예정",
    "0049007": "대학 졸업",
    "0049008": "석·박사",
    "0049009": "기타",
    "0049010": "제한없음",
}

# 정책특화요건코드(sbizCd, 0014) - 콤마로 여러 개 올 수 있음 (실측: 24건)
ONTONG_SBIZ_CD_MAP = {
    "0014001": "중소기업",
    "0014002": "여성",
    "0014003": "기초생활수급자",
    "0014004": "한부모가정",
    "0014005": "장애인",
    "0014006": "농업인",
    "0014007": "군인",
    "0014008": "지역인재",
    "0014009": "기타",
    "0014010": "제한없음",
}

# 정책전공요건코드(plcyMajorCd, 0011) - 콤마로 여러 개 올 수 있음 (실측 확인)
ONTONG_MAJOR_CD_MAP = {
    "0011001": "인문계열",
    "0011002": "사회계열",
    "0011003": "상경계열",
    "0011004": "이학계열",
    "0011005": "공학계열",
    "0011006": "예체능계열",
    "0011007": "농산업계열",
    "0011008": "기타",
    "0011009": "제한없음",
}

_NO_RESTRICTION_LABELS = {"제한없음"}


def decode_multi_code(raw_value: Optional[str], code_map: Dict[str, str]) -> List[str]:
    """
    "0049005,0049006" 처럼 콤마로 여러 코드가 올 수 있는 필드를 라벨 리스트로 바꾼다.
    "제한없음"은 조건이 없다는 뜻이라 리스트에서 뺀다(빈 리스트 = 조건 없음).
    모르는 코드값은 원본 코드를 그대로 남겨서 데이터가 사라지지 않게 한다.
    """
    if not raw_value:
        return []

    labels = []
    for code in raw_value.split(","):
        code = code.strip()
        if not code:
            continue
        label = code_map.get(code, code)
        if label in _NO_RESTRICTION_LABELS:
            continue
        labels.append(label)

    return labels


def decode_single_code(raw_value: Optional[str], code_map: Dict[str, str]) -> Optional[str]:
    """
    값이 1개만 오는 코드 필드를 라벨로 바꾼다. "제한없음"이거나 값이 없으면 None.
    """
    code = (raw_value or "").strip()
    if not code:
        return None

    label = code_map.get(code, code)
    if label in _NO_RESTRICTION_LABELS:
        return None

    return label


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
    ("농업인", ["농업인", "귀농", "농업 종사자", "영농"]),
    ("프리랜서", ["프리랜서", "특수형태근로종사자", "예술인"]),
    ("일용근로자", ["일용근로자", "일용직"]),
    ("단기근로자", ["단기근로자", "단기근로"]),
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
