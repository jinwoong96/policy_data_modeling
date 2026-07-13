### 2) 공통 스키마 정의
# schema.py
#
# 온통청년 API와 지자체복지서비스 API는 필드명도, 개념도 서로 다르다
# (예: 온통청년의 "신청기간"은 실제 신청 접수 기간이지만, 지자체복지서비스에는
#  그런 개념이 없고 "시행기간"만 있다). 그래서 특정 API의 필드명을 그대로
# 따라가지 않고, 서비스에서 실제로 쓸 개념 단위로 스키마를 새로 정의한다.
#
# 필드 설명
# ---------
# source                 : "ontong" | "welfare"  (원본 출처)
# source_id              : 원본 시스템의 고유 ID (plcyNo 또는 servId)
# title                  : 정책/서비스명
# agency                 : 소관/담당 기관·부서명
# region_names           : 표준화된 지역명 리스트 (["전국"] / ["OO도 전체"] / ["OO시 OO구"] 등)
# life_cycle             : 생애주기 태그 (예: ["청년"], welfare는 여러 개일 수 있음)
# theme_keywords         : 관심주제/카테고리 키워드
# employment_status      : 표준화된 재직/취업 상태 태그 (자유 텍스트에서 추출, 없으면 빈 리스트)
# apply_period_type      : "상시" | "마감" | "특정기간" | "확인필요"  (신청 접수 기간 - 정보가 없는 출처는 "확인필요")
# apply_period           : "YYYY-MM-DD ~ YYYY-MM-DD" | None
# service_period_type    : "상시" | "기간한정" | "확인필요"  (사업/제도 시행 기간)
# service_period         : "YYYY-MM-DD ~ YYYY-MM-DD" | None
# target_text            : 지원대상 원문 (그대로 보존, 사람이 읽는 용도)
# target_age_min         : 나이 하한 (int | None)
# target_age_max         : 나이 상한 (int | None)
# target_income_condition: 소득 조건 원문 스니펫 (예: "중위소득 150% 이하") | None
# support_text           : 지원내용 원문 (금액/한도 등 포함)
# apply_method           : 신청 방법
# link                   : 신청 또는 공식 안내 페이지 링크 (없으면 빈 문자열)
# raw                    : 원본 레코드 전체 (역추적/디버깅용, 그대로 보존)

COMMON_SCHEMA_FIELDS = [
    "source",
    "source_id",
    "title",
    "agency",
    "region_names",
    "life_cycle",
    "theme_keywords",
    "employment_status",
    "apply_period_type",
    "apply_period",
    "service_period_type",
    "service_period",
    "target_text",
    "target_age_min",
    "target_age_max",
    "target_income_condition",
    "support_text",
    "apply_method",
    "link",
    "raw",
]


def new_common_record(**kwargs) -> dict:
    """
    공통 스키마 기본값으로 dict를 만들고 kwargs로 덮어쓴다.
    어댑터에서 빠뜨린 필드가 있어도 항상 전체 필드가 채워지도록 보장한다.
    """
    record = {
        "source": "",
        "source_id": "",
        "title": "",
        "agency": "",
        "region_names": [],
        "life_cycle": [],
        "theme_keywords": [],
        "employment_status": [],
        "apply_period_type": "확인필요",
        "apply_period": None,
        "service_period_type": "확인필요",
        "service_period": None,
        "target_text": "",
        "target_age_min": None,
        "target_age_max": None,
        "target_income_condition": None,
        "support_text": "",
        "apply_method": "",
        "link": "",
        "raw": None,
    }
    record.update(kwargs)
    return record
