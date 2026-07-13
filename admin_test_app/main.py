### 관리자 수동 정책추가 - 로컬 테스트용 백엔드
# main.py
#
# 목적: bene_backend/관리자 웹에 실제로 붙이기 전에, "폼 입력 -> 검증/중복체크 -> 저장"
# 플로우가 화면에서 어떻게 동작하는지 로컬에서 클릭해보기 위한 독립 실행 앱.
#
# 실행: uvicorn main:app --reload --port 8010
# 접속: http://localhost:8010

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from schema import COMMON_SCHEMA_FIELDS, new_common_record
from validate import validate_record
from dedup import find_duplicates_for_new, record_for_display
from extract import extract_policy_fields

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
EXISTING_FILE = DATA_DIR / "common_policies.json"  # 기존 DB 스탠드인 (온통청년+지자체 통합본)
MANUAL_FILE = DATA_DIR / "manual_policies.json"    # 이 테스트앱에서 관리자가 추가한 것들

app = FastAPI(title="정책 관리자 수동추가 - 로컬 테스트")


# ---------------------------------------------------------------------------
# 데이터 로드/저장 (실제 서비스에서는 이 부분이 RDS policy 테이블 조회/insert로 대체됨)
# ---------------------------------------------------------------------------

def load_existing() -> List[Dict[str, Any]]:
    with open(EXISTING_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_manual() -> List[Dict[str, Any]]:
    if not MANUAL_FILE.exists():
        return []
    with open(MANUAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_manual(records: List[Dict[str, Any]]) -> None:
    MANUAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MANUAL_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


EXISTING_RECORDS = load_existing()  # 서버 시작 시 1회 로드 (2,869건)


def all_records() -> List[Dict[str, Any]]:
    return EXISTING_RECORDS + load_manual()


# ---------------------------------------------------------------------------
# 폼 필드 메타 - schema.py의 COMMON_SCHEMA_FIELDS 기준으로 프론트 폼을 그린다.
# 필드가 schema.py에서 추가/삭제되면 여기만 맞춰주면 폼도 같이 바뀐다.
# ---------------------------------------------------------------------------

LIST_FIELDS = {"region_names", "life_cycle", "theme_keywords", "employment_status"}
TEXTAREA_FIELDS = {"target_text", "support_text"}
INT_FIELDS = {"target_age_min", "target_age_max"}
SELECT_FIELDS = {
    "apply_period_type": ["상시", "마감", "특정기간", "확인필요"],
    "service_period_type": ["상시", "기간한정", "확인필요"],
}
HIDDEN_FIELDS = {"source", "source_id", "raw"}  # source/source_id는 서버가 자동 채움, raw는 원본 API용이라 수동입력 없음

FIELD_LABELS = {
    "source": "출처",
    "source_id": "원본 ID",
    "title": "정책/서비스명",
    "agency": "소관 기관·부서",
    "region_names": "지역명 (쉼표로 구분, 예: 서울특별시 전체)",
    "life_cycle": "생애주기 태그 (쉼표로 구분)",
    "theme_keywords": "관심주제 키워드 (쉼표로 구분)",
    "employment_status": "재직/취업 상태 태그 (쉼표로 구분)",
    "apply_period_type": "신청기간 유형",
    "apply_period": "신청기간 (YYYY-MM-DD ~ YYYY-MM-DD)",
    "service_period_type": "시행기간 유형",
    "service_period": "시행기간 (YYYY-MM-DD ~ YYYY-MM-DD)",
    "target_text": "지원대상 (원문)",
    "target_age_min": "나이 하한",
    "target_age_max": "나이 상한",
    "target_income_condition": "소득 조건",
    "support_text": "지원내용",
    "apply_method": "신청 방법",
    "link": "신청/안내 페이지 링크",
}


TEST_CASES_FILE = DATA_DIR / "test_cases.json"


@app.get("/api/test-cases")
def get_test_cases():
    with open(TEST_CASES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _field_type(name: str) -> str:
    if name in LIST_FIELDS:
        return "tags"
    if name in TEXTAREA_FIELDS:
        return "textarea"
    if name in INT_FIELDS:
        return "int"
    if name in SELECT_FIELDS:
        return "select"
    return "text"


@app.get("/api/schema")
def get_schema():
    fields = []
    for name in COMMON_SCHEMA_FIELDS:
        if name in HIDDEN_FIELDS:
            continue
        options = SELECT_FIELDS.get(name)
        fields.append({
            "name": name,
            "label": FIELD_LABELS.get(name, name),
            "type": _field_type(name),
            "options": options,
        })

    # 비교 화면용: raw만 빼고 source/source_id 포함 전체 필드 (표시 순서 그대로)
    compare_fields = [
        {
            "name": name,
            "label": FIELD_LABELS.get(name, name),
            "type": _field_type(name),
        }
        for name in COMMON_SCHEMA_FIELDS
        if name != "raw"
    ]

    return {"fields": fields, "compare_fields": compare_fields}


# ---------------------------------------------------------------------------
# 입력 -> 공통 스키마 레코드 변환
# ---------------------------------------------------------------------------

class PolicyInput(BaseModel):
    title: str = ""
    agency: str = ""
    region_names: List[str] = []
    life_cycle: List[str] = []
    theme_keywords: List[str] = []
    employment_status: List[str] = []
    apply_period_type: str = "확인필요"
    apply_period: Optional[str] = None
    service_period_type: str = "확인필요"
    service_period: Optional[str] = None
    target_text: str = ""
    target_age_min: Optional[int] = None
    target_age_max: Optional[int] = None
    target_income_condition: Optional[str] = None
    support_text: str = ""
    apply_method: str = ""
    link: str = ""


def build_record(payload: PolicyInput, source_id: str) -> Dict[str, Any]:
    return new_common_record(
        source="manual",
        source_id=source_id,
        raw=None,
        **payload.model_dump(),
    )


# ---------------------------------------------------------------------------
# API: 검사 (저장 안 함) - validate.py + dedup.py 재사용
# ---------------------------------------------------------------------------

@app.post("/api/extract")
async def extract_from_document(
    file: UploadFile = File(None),
    pasted_text: str = Form(None),
):
    if (file is None or not file.filename) and not (pasted_text and pasted_text.strip()):
        raise HTTPException(status_code=400, detail="파일 또는 텍스트를 입력해주세요.")

    file_bytes = None
    media_type = None
    if file is not None and file.filename:
        file_bytes = await file.read()
        media_type = file.content_type
        name_lower = file.filename.lower()
        if not media_type or media_type == "application/octet-stream":
            if name_lower.endswith(".pdf"):
                media_type = "application/pdf"
            elif name_lower.endswith((".png",)):
                media_type = "image/png"
            elif name_lower.endswith((".jpg", ".jpeg")):
                media_type = "image/jpeg"
        if name_lower.endswith(".hwp"):
            raise HTTPException(
                status_code=400,
                detail="HWP는 직접 지원하지 않습니다. PDF로 변환 후 업로드해주세요.",
            )

    try:
        extracted = extract_policy_fields(
            text=pasted_text, file_bytes=file_bytes, file_media_type=media_type
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 추출 요청 실패: {e}")

    filled = [k for k, v in extracted.items() if v not in (None, "", [])]
    empty = [k for k, v in extracted.items() if v in (None, "", [])]

    return {"extracted": extracted, "filled_fields": filled, "empty_fields": empty}


@app.post("/api/check")
def check_policy(payload: PolicyInput):
    # 검사 단계에서는 임시 source_id를 씀 (아직 확정 저장 전이라 실제 채번 불필요)
    record = build_record(payload, source_id="(저장 시 자동 생성)")

    issues = validate_record(record)
    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]

    duplicates = find_duplicates_for_new(record, all_records())

    return {
        "errors": errors,
        "warnings": warnings,
        "duplicate_candidates": duplicates,
        "can_save": len(errors) == 0,
        "new_record": record_for_display(record),
    }


# ---------------------------------------------------------------------------
# API: 저장 - 관리자가 검사 결과를 확인한 뒤 최종 확정할 때 호출
# ---------------------------------------------------------------------------

@app.post("/api/policies")
def create_policy(payload: PolicyInput):
    source_id = f"manual-{uuid.uuid4().hex[:12]}"
    record = build_record(payload, source_id=source_id)

    issues = validate_record(record)
    errors = [i for i in issues if i["level"] == "error"]
    if errors:
        # 프론트에서 /check로 이미 걸렀어야 하지만, 우회 방지를 위해 서버에서도 재검증
        raise HTTPException(status_code=400, detail={"errors": errors})

    warnings = [i for i in issues if i["level"] == "warning"]
    if warnings:
        record["_warnings"] = warnings

    manual_records = load_manual()
    manual_records.append(record)
    save_manual(manual_records)

    return record


@app.get("/api/policies")
def list_policies(q: Optional[str] = None, limit: int = 30):
    records = all_records()
    if q:
        q_lower = q.lower()
        records = [r for r in records if q_lower in (r.get("title") or "").lower()]
    return {
        "total": len(records),
        "manual_count": len(load_manual()),
        "existing_count": len(EXISTING_RECORDS),
        "items": records[:limit],
    }


# ---------------------------------------------------------------------------
# 정적 프론트 서빙
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
