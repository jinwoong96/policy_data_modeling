### 공고문 자동추출 - AI가 폼 칸을 채워주되, 저장/검증은 절대 대신하지 않는다.
# extract.py (watsonx.ai 버전)
#
# 관리자가 공고문 파일(PDF/이미지)이나 텍스트를 주면, 그 안에서 공통 스키마
# 필드에 해당하는 값을 뽑아 "초안"으로 돌려준다. 이 초안은 폼을 채우는 데만
# 쓰이고, 그 뒤로는 여전히 validate.py + dedup.py를 통과해야 저장된다.
#
# 필드 목록(FIELD_DESCRIPTIONS/LIST_FIELDS 등)이 아니라 COMMON_SCHEMA_FIELDS를
# 기준으로 프롬프트를 만들기 때문에, schema.py에 필드가 추가되면 프롬프트에도
# 자동으로 나열된다. 다만 필드 "설명"과 "타입"(list/int/enum)은 AI에게 정확한
# 지시를 주기 위해 필드별로 사람이 채워둔 메타데이터가 필요해서 아래에 별도로
# 정의한다 - 새 필드를 추가하면 FIELD_DESCRIPTIONS/타입 집합에도 항목을 추가해야
# 프롬프트 설명이 비어있지 않다(안 넣어도 동작은 하지만 AI가 추측에 의존하게 됨).
#
# watsonx.ai는 Claude와 달리 PDF를 통째로 읽는 기능이 없다. 그래서 PDF는
# (1) 텍스트 레이어가 있으면 pypdf로 텍스트만 뽑아서 텍스트 모델에 보내고,
# (2) 텍스트 레이어가 거의 없으면(스캔본) PyMuPDF로 페이지를 이미지로 렌더링해서
#     vision 모델(예: llama-3-2-90b-vision-instruct)에 보낸다.
# 순수 이미지 업로드는 바로 vision 모델로 보낸다.

import io
import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()  # policy_data_modeling/.env 파일이 있으면 여기서 자동으로 읽어서 os.environ에 채워준다

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

from schema import COMMON_SCHEMA_FIELDS

WATSONX_URL = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID")
WATSONX_API_KEY = os.environ.get("WATSONX_API_KEY")

TEXT_MODEL_ID = os.environ.get("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")
VISION_MODEL_ID = os.environ.get("WATSONX_VISION_MODEL_ID", "meta-llama/llama-3-2-90b-vision-instruct")

# 텍스트 레이어가 이 길이 미만이면 "스캔본"으로 보고 이미지 렌더링 경로로 전환한다.
MIN_PDF_TEXT_LENGTH = 30
MAX_RENDERED_PAGES = 3  # vision 모델에 한 번에 넘길 최대 페이지 수 (비용/속도 방어용)

# source/source_id/raw는 서버가 채우는 값이라 AI 추출 대상이 아니다.
# view_count/last_updated는 공고문 "내용"이 아니라 시스템이 관리하는 메타데이터라서
# (조회수는 아직 등록 전이라 의미가 없고, 최종수정일은 저장 시점 기준으로 서버가 채움)
# 마찬가지로 추출 대상에서 뺀다.
EXTRACT_EXCLUDE_FIELDS = {"source", "source_id", "raw", "view_count", "last_updated"}

LIST_FIELDS = {
    "region_names", "life_cycle", "theme_keywords", "employment_status",
    "provision_method", "special_target_groups", "education_condition", "major_condition",
}
INT_FIELDS = {"target_age_min", "target_age_max"}
# 값이 항상 있어야 하는 enum (허용값 밖이면 "확인필요"로 대체)
ENUM_FIELDS = {
    "apply_period_type": ["상시", "마감", "특정기간", "확인필요"],
    "service_period_type": ["상시", "기간한정", "확인필요"],
}
# 값이 없을 수도 있는 enum (조건 자체가 없으면 null - "확인필요"로 대체하면 안 됨)
NULLABLE_ENUM_FIELDS = {
    "marital_status": ["기혼", "미혼"],
}

FIELD_DESCRIPTIONS = {
    "title": "정책/서비스명. 공고문 제목을 그대로 사용.",
    "agency": "소관·담당 기관 또는 부서명.",
    "region_names": "지원 대상 지역. 예: [\"서울특별시 전체\"], [\"전국\"], 구/군 단위면 \"경상북도 고령군\"처럼 \"{시도} {시군구}\" 형식. 전국 대상이면 [\"전국\"].",
    "life_cycle": "생애주기 태그. 예: [\"청년\"], [\"신혼부부\"]. 명시 안 되어 있으면 빈 배열.",
    "theme_keywords": "관심주제/카테고리 키워드 (예: 주거, 창업, 취업).",
    "employment_status": "재직/취업 상태 조건 (재직자, 미취업자, 구직자 등). 명시 안 되어 있으면 빈 배열.",
    "apply_period_type": "신청 접수 기간 유형. 반드시 허용값 중 하나.",
    "apply_period": "신청 접수 기간. \"YYYY-MM-DD ~ YYYY-MM-DD\" 형식. 모르면 null.",
    "service_period_type": "사업/제도 시행 기간 유형. 반드시 허용값 중 하나.",
    "service_period": "사업 시행 기간. \"YYYY-MM-DD ~ YYYY-MM-DD\" 형식. 모르면 null.",
    "target_text": "지원대상을 설명하는 원문. 문서 표현을 최대한 그대로 보존.",
    "target_age_min": "나이 하한 (정수, 만 나이). 명시 안 되어 있으면 null.",
    "target_age_max": "나이 상한 (정수, 만 나이). 명시 안 되어 있으면 null.",
    "target_income_condition": "소득 조건 원문 스니펫. 예: \"중위소득 150% 이하\". 없으면 null.",
    "support_text": "지원내용 원문 (금액/한도 등 포함).",
    "apply_method": "신청 방법 (온라인/방문/우편 등, 구체적으로).",
    "link": "신청 또는 공식 안내 페이지 링크. 문서에 명시된 URL이 없으면 빈 문자열.",
    "description": "정책/서비스 설명·취지 (지원내용과 별개로, 왜 만들어졌는지 간단한 배경 설명). 없으면 빈 문자열.",
    "provision_method": "제공방식 태그. 예: [\"보조금\"], [\"현금지급\",\"바우처\"]. 명시 안 되어 있으면 빈 배열.",
    "special_target_groups": "특수 대상군 태그. 예: [\"장애인\",\"한부모가정\"]. 명시 안 되어 있으면 빈 배열.",
    "education_condition": "학력 조건 태그. 예: [\"대학 재학\",\"고졸 이상\"]. 조건이 없으면 빈 배열.",
    "major_condition": "전공계열 조건 태그. 예: [\"공학계열\"]. 조건이 없으면 빈 배열.",
    "marital_status": "혼인상태 조건. \"기혼\" 또는 \"미혼\"만 가능. 조건이 명시되어 있지 않으면 null.",
}


def _field_type(name: str) -> str:
    if name in LIST_FIELDS:
        return "list[string]"
    if name in INT_FIELDS:
        return "int | null"
    if name in ENUM_FIELDS:
        return f"enum{ENUM_FIELDS[name]}"
    if name in NULLABLE_ENUM_FIELDS:
        return f"enum{NULLABLE_ENUM_FIELDS[name]} | null"
    return "string"


def _build_system_prompt() -> str:
    lines = [
        "당신은 청년정책/복지서비스 공고문에서 정보를 추출하는 도구입니다.",
        "아래 필드 목록에 맞춰 공고문 내용을 분석하고, 반드시 JSON 객체 하나만 응답하세요.",
        "설명, 코드블록(```), 마크다운 없이 순수 JSON 텍스트만 출력합니다.",
        "",
        "규칙:",
        "- 문서에 명시되지 않은 정보는 절대 추측하지 말고 string은 \"\", list는 [], "
        "int/기간/enum-null 필드는 null로 둡니다.",
        "- target_text, support_text는 문서 표현을 요약하지 말고 최대한 원문 그대로 옮깁니다.",
        "- apply_period_type / service_period_type은 반드시 지정된 허용값 중 하나만 씁니다.",
        "- marital_status는 \"기혼\"/\"미혼\"이 명시된 경우에만 채우고, 그 외에는 null로 둡니다.",
        "- 날짜는 반드시 YYYY-MM-DD 형식으로 변환합니다 (예: 2026.4.1. → 2026-04-01).",
        "",
        "필드 목록:",
    ]
    for name in COMMON_SCHEMA_FIELDS:
        if name in EXTRACT_EXCLUDE_FIELDS:
            continue
        desc = FIELD_DESCRIPTIONS.get(name, "")
        lines.append(f"- {name} ({_field_type(name)}): {desc}")

    lines.append("")
    lines.append("JSON key는 위 필드명과 정확히 일치해야 하고, 필드는 전부 포함해야 합니다.")
    return "\n".join(lines)


def _extract_json_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    return text.strip()


def _sanitize(raw: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in COMMON_SCHEMA_FIELDS:
        if name in EXTRACT_EXCLUDE_FIELDS:
            continue
        val = raw.get(name)

        if name in LIST_FIELDS:
            if isinstance(val, list):
                out[name] = [str(v).strip() for v in val if str(v).strip()]
            elif isinstance(val, str) and val.strip():
                out[name] = [v.strip() for v in val.split(",") if v.strip()]
            else:
                out[name] = []
        elif name in INT_FIELDS:
            try:
                out[name] = int(val) if val is not None and str(val).strip() != "" else None
            except (ValueError, TypeError):
                out[name] = None
        elif name in ENUM_FIELDS:
            out[name] = val if val in ENUM_FIELDS[name] else "확인필요"
        elif name in NULLABLE_ENUM_FIELDS:
            out[name] = val if val in NULLABLE_ENUM_FIELDS[name] else None
        else:
            out[name] = "" if val is None else str(val)
            if name in ("apply_period", "service_period", "target_income_condition") and not out[name]:
                out[name] = None

    return out


def _get_model(model_id: str) -> ModelInference:
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        raise ValueError(
            "WATSONX_API_KEY / WATSONX_PROJECT_ID 환경변수가 설정되어 있지 않습니다."
        )
    credentials = Credentials(url=WATSONX_URL, api_key=WATSONX_API_KEY)
    return ModelInference(model_id=model_id, credentials=credentials, project_id=WATSONX_PROJECT_ID)


def _chat(model_id: str, content_blocks: List[Dict[str, Any]]) -> str:
    model = _get_model(model_id)
    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": content_blocks},
    ]
    response = model.chat(messages=messages)
    return response["choices"][0]["message"]["content"]


def _pdf_text_layer(file_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    parts = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(parts).strip()


def _pdf_to_images(file_bytes: bytes, max_pages: int = MAX_RENDERED_PAGES) -> List[bytes]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(dpi=200)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def _image_content_block(image_bytes: bytes, media_type: str = "image/png") -> Dict[str, Any]:
    import base64

    b64 = base64.b64encode(image_bytes).decode()
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{b64}"},
    }


def extract_policy_fields(
    text: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    file_media_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    text 그리고/또는 파일(PDF/이미지) 바이트를 받아 공통 스키마 필드 dict를 반환한다.
    실패 시 예외를 던진다 (호출부에서 HTTPException으로 변환).
    """
    if not text and not file_bytes:
        raise ValueError("텍스트 또는 파일 중 하나는 있어야 합니다.")

    content: List[Dict[str, Any]] = []
    model_id = TEXT_MODEL_ID

    if file_bytes:
        if file_media_type == "application/pdf":
            pdf_text = _pdf_text_layer(file_bytes)
            if len(pdf_text) >= MIN_PDF_TEXT_LENGTH:
                content.append({"type": "text", "text": f"[공고문 PDF 텍스트]\n{pdf_text}"})
            else:
                # 텍스트 레이어가 거의 없음 = 스캔본으로 판단, 페이지를 이미지로 렌더링해서 vision 모델로 전환
                model_id = VISION_MODEL_ID
                images = _pdf_to_images(file_bytes)
                if not images:
                    raise ValueError("PDF에서 텍스트도 이미지도 추출하지 못했습니다.")
                for img in images:
                    content.append(_image_content_block(img, "image/png"))
        elif file_media_type and file_media_type.startswith("image/"):
            model_id = VISION_MODEL_ID
            content.append(_image_content_block(file_bytes, file_media_type))
        else:
            raise ValueError(
                f"지원하지 않는 파일 형식입니다: {file_media_type!r}. "
                "PDF, PNG, JPG만 지원합니다. HWP는 PDF로 변환 후 업로드해주세요."
            )

    if text and text.strip():
        content.append({"type": "text", "text": f"[공고문 텍스트]\n{text.strip()}"})

    content.append({"type": "text", "text": "위 공고문에서 필드를 추출해 JSON으로만 응답하세요."})

    raw_text = _chat(model_id, content)
    json_text = _extract_json_text(raw_text)

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI 응답을 JSON으로 해석하지 못했습니다: {e}\n원본 응답: {raw_text[:500]}")

    return _sanitize(parsed)
