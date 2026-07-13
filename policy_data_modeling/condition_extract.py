### 5) 비정형 조건 추출 - 지원대상 자유 텍스트에서 나이/소득 조건을 정규표현식으로 추출
# condition_extract.py
#
# 온통청년은 나이 조건이 이미 구조화된 필드(sprtTrgtMinAge/MaxAge)로 있어서
# 이 모듈이 굳이 필요 없지만, 지자체복지서비스는 나이/소득 조건이 전부
# 자유 텍스트(sprtTrgtCn, slctCritCn) 안에 섞여 있어서 정규표현식으로 뽑아낸다.
#
# 실제 welfare_detail_raw.json 236건으로 패턴을 검증한 결과 나이 조건은
# 약 92%(218/236), 소득 조건은 약 45%(105/236, 중위소득+연소득 합산) 커버된다.
# 나머지는 텍스트가 너무 불규칙하거나(예: "고교졸업예정자~39세") 애초에
# 나이/소득 조건이 명시돼 있지 않은 경우라서, 못 뽑으면 None으로 남기고
# target_text 원문은 항상 보존하므로 정보 손실은 없다.
#
# 이 정규표현식으로 못 뽑는 비율이 실제 운영 중 너무 높아지면, 여기 함수들의
# 인터페이스(extract_age_range/extract_income_condition)를 유지한 채
# watsonx 호출로 교체하는 폴백을 추가하면 된다 (policy_card_generator.py의
# WatsonxPolicySummaryGenerator 패턴을 그대로 재사용 가능).

import re
from typing import Optional, Tuple


_AGE_RANGE_PAT = re.compile(
    r"(?:만\s*)?(\d{1,2})\s*세?\s*(?:이상)?\s*(?:[~\-∼～]|부터)\s*(?:만\s*)?(\d{1,2})\s*세\s*(?:이하|까지)?"
)
_AGE_MIN_ONLY_PAT = re.compile(r"(?:만\s*)?(\d{1,2})\s*세\s*이상")
_AGE_MAX_ONLY_PAT = re.compile(r"(?:만\s*)?(\d{1,2})\s*세\s*이하")
_AGE_SINGLE_PAT = re.compile(r"만\s*(\d{1,2})\s*세(?!\s*(?:이상|이하))")

_MEDIAN_INCOME_PAT = re.compile(r"(?:기준\s*)?중위소득\s*\d{1,3}\s*%\s*(?:이하|이내)")
_ANNUAL_INCOME_PAT = re.compile(r"연\s*소득\s*[\d,]*[천만억원]+\s*(?:이하|이내)")


def extract_age_range(text: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    자유 텍스트에서 나이 범위를 뽑는다. 못 찾으면 (None, None).
    """
    if not text:
        return None, None

    match = _AGE_RANGE_PAT.search(text)
    if match:
        lo, hi = int(match.group(1)), int(match.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    match = _AGE_MIN_ONLY_PAT.search(text)
    if match:
        return int(match.group(1)), None

    match = _AGE_MAX_ONLY_PAT.search(text)
    if match:
        return None, int(match.group(1))

    match = _AGE_SINGLE_PAT.search(text)
    if match:
        age = int(match.group(1))
        return age, age

    return None, None


def extract_income_condition(text: Optional[str]) -> Optional[str]:
    """
    자유 텍스트에서 소득 조건 문구를 그대로 뽑아 반환한다(표준화된 숫자로 바꾸지 않고
    "중위소득 150% 이하" 같은 원문 매치 그대로 보존 - 잘못 변환하는 것보다 안전).
    중위소득 기준을 우선하고, 없으면 연소득 기준을 본다.
    """
    if not text:
        return None

    match = _MEDIAN_INCOME_PAT.search(text)
    if match:
        return match.group(0)

    match = _ANNUAL_INCOME_PAT.search(text)
    if match:
        return match.group(0)

    return None


def extract_conditions(text: Optional[str]) -> dict:
    age_min, age_max = extract_age_range(text)
    return {
        "age_min": age_min,
        "age_max": age_max,
        "income_condition": extract_income_condition(text),
    }
