### 6) 검증 및 오류 분리 - 온통청년 스키마 기준으로 문제 있는 레코드를 분리
# validate.py

from typing import Any, Dict, List, Tuple

from ontong_schema import UNIFIED_SCHEMA_FIELDS

_DIGIT_OR_EMPTY_FIELDS = [
    "sprtTrgtMinAge", "sprtTrgtMaxAge", "earnMinAmt", "earnMaxAmt", "inqCnt",
]


def _add(issues: List[Dict[str, str]], level: str, field: str, message: str) -> None:
    issues.append({"level": level, "field": field, "message": message})


def validate_record(record: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for field in UNIFIED_SCHEMA_FIELDS:
        if field not in record:
            _add(issues, "error", field, "필수 필드가 없습니다.")

    if not (record.get("plcyNo") or "").strip():
        _add(issues, "error", "plcyNo", "plcyNo가 비어 있습니다.")

    if not (record.get("plcyNm") or "").strip():
        _add(issues, "error", "plcyNm", "plcyNm이 비어 있습니다.")

    if record.get("source") not in ("ontong", "welfare"):
        _add(issues, "error", "source", f"알 수 없는 source 값: {record.get('source')!r}")

    for field in _DIGIT_OR_EMPTY_FIELDS:
        value = record.get(field)
        if value not in (None, "") and not str(value).strip().isdigit():
            _add(issues, "warning", field, f"숫자 형식이 아닙니다: {value!r}")

    min_age = record.get("sprtTrgtMinAge")
    max_age = record.get("sprtTrgtMaxAge")
    if min_age and max_age and str(min_age).isdigit() and str(max_age).isdigit():
        if int(min_age) > int(max_age):
            _add(issues, "warning", "sprtTrgtMinAge/MaxAge", f"나이 하한({min_age})이 상한({max_age})보다 큽니다.")

    zip_cd = (record.get("zipCd") or "").strip()
    if zip_cd and not all(part.strip().isdigit() for part in zip_cd.split(",") if part.strip()):
        _add(issues, "warning", "zipCd", f"숫자 코드 목록 형식이 아닙니다: {zip_cd!r}")

    for field in ("aplyUrlAddr", "refUrlAddr1", "refUrlAddr2"):
        value = (record.get(field) or "").strip()
        if value and not value.startswith("http"):
            _add(issues, "warning", field, f"URL 형식이 아닌 것 같습니다: {value!r}")

    if not (record.get("plcySprtCn") or "").strip() and not (record.get("addAplyQlfcCndCn") or "").strip():
        _add(issues, "warning", "plcySprtCn/addAplyQlfcCndCn", "지원내용, 신청자격 조건이 둘 다 비어 있습니다.")

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
                "plcyNo": record.get("plcyNo"),
                "plcyNm": record.get("plcyNm"),
                "issues": issues,
            })
            continue

        if warnings:
            record = dict(record)
            record["_warnings"] = warnings

        valid.append(record)

    return valid, invalid
