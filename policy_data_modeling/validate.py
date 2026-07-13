### 6) 검증 및 오류 분리 - 공통 스키마 기준으로 문제 있는 레코드를 분리
# validate.py

from typing import Any, Dict, List, Tuple

from schema import COMMON_SCHEMA_FIELDS


ALLOWED_APPLY_PERIOD_TYPES = {"상시", "마감", "특정기간", "확인필요"}
ALLOWED_SERVICE_PERIOD_TYPES = {"상시", "기간한정", "확인필요"}

LIST_FIELDS = [
    "region_names", "life_cycle", "theme_keywords", "employment_status",
    "provision_method", "special_target_groups", "education_condition",
    "major_condition",
]


def _add(issues: List[Dict[str, str]], level: str, field: str, message: str) -> None:
    issues.append({"level": level, "field": field, "message": message})


def validate_record(record: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for field in COMMON_SCHEMA_FIELDS:
        if field not in record:
            _add(issues, "error", field, "필수 필드가 없습니다.")

    if not (record.get("source_id") or "").strip():
        _add(issues, "error", "source_id", "source_id가 비어 있습니다.")

    if not (record.get("title") or "").strip():
        _add(issues, "error", "title", "title이 비어 있습니다.")

    if record.get("source") not in ("ontong", "welfare", "manual"):
        _add(issues, "error", "source", f"알 수 없는 source 값: {record.get('source')!r}")

    for field in LIST_FIELDS:
        if not isinstance(record.get(field), list):
            _add(issues, "error", field, "리스트 타입이 아닙니다.")

    if record.get("apply_period_type") not in ALLOWED_APPLY_PERIOD_TYPES:
        _add(issues, "error", "apply_period_type", f"허용되지 않는 값: {record.get('apply_period_type')!r}")

    if record.get("service_period_type") not in ALLOWED_SERVICE_PERIOD_TYPES:
        _add(issues, "error", "service_period_type", f"허용되지 않는 값: {record.get('service_period_type')!r}")

    age_min = record.get("target_age_min")
    age_max = record.get("target_age_max")
    for name, value in (("target_age_min", age_min), ("target_age_max", age_max)):
        if value is not None and not isinstance(value, int):
            _add(issues, "error", name, f"정수가 아닙니다: {value!r}")
    if isinstance(age_min, int) and isinstance(age_max, int) and age_min > age_max:
        _add(issues, "warning", "target_age_min/max", f"나이 하한({age_min})이 상한({age_max})보다 큽니다.")
    if isinstance(age_min, int) and not (0 <= age_min <= 120):
        _add(issues, "warning", "target_age_min", f"나이 값이 비정상적입니다: {age_min}")
    if isinstance(age_max, int) and not (0 <= age_max <= 120):
        _add(issues, "warning", "target_age_max", f"나이 값이 비정상적입니다: {age_max}")

    if not (record.get("target_text") or "").strip() and not (record.get("support_text") or "").strip():
        _add(issues, "warning", "target_text/support_text", "지원대상, 지원내용이 둘 다 비어 있습니다.")

    link = record.get("link") or ""
    if link and not link.startswith("http"):
        _add(issues, "warning", "link", f"URL 형식이 아닌 것 같습니다: {link!r}")

    view_count = record.get("view_count")
    if view_count is not None and not isinstance(view_count, int):
        _add(issues, "warning", "view_count", f"정수가 아닙니다: {view_count!r}")

    marital_status = record.get("marital_status")
    if marital_status is not None and marital_status not in ("기혼", "미혼"):
        _add(issues, "warning", "marital_status", f"예상하지 못한 값: {marital_status!r}")

    return issues


def split_valid_invalid(
    records: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    error 레벨 이슈가 하나라도 있으면 invalid로 분리한다.
    warning만 있는 레코드는 valid로 두되, 레코드 안에 "_warnings"로 남긴다.
    """
    valid: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []

    for record in records:
        issues = validate_record(record)
        errors = [i for i in issues if i["level"] == "error"]
        warnings = [i for i in issues if i["level"] == "warning"]

        if errors:
            invalid.append({
                "source": record.get("source"),
                "source_id": record.get("source_id"),
                "title": record.get("title"),
                "issues": issues,
            })
            continue

        if warnings:
            record = dict(record)
            record["_warnings"] = warnings

        valid.append(record)

    return valid, invalid
