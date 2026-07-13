# 정책 관리자 수동추가 - 로컬 테스트앱

관리자가 정책을 수동으로 추가할 때, DB에 반영하기 전에 **필드 검증 + 중복탐지 + AI 자동채우기**가
어떻게 동작하는지 화면에서 직접 클릭해보기 위한 독립 실행 앱입니다.

`admin_test_app/`에 있던 같은 기능을 이 폴더(`policy_data_modeling`) 안에서 새로 짰습니다.
`admin_test_app`은 파이프라인 초기 커밋 시점의 `schema.py`(20필드)를 기준으로 만들어져서,
이후 추가된 8개 필드(description, provision_method, special_target_groups,
education_condition, major_condition, marital_status, view_count, last_updated)가 반영되지
않은 상태였습니다. 이 버전은 지금 이 폴더의 `schema.py`(28필드)를 그대로 기준으로 삼고,
같은 문제가 다시 생기지 않도록 구조를 하나 바꿨습니다.

## admin_test_app과 다른 점

- **`main.py`가 필드를 하드코딩하지 않습니다.** 이전 버전은 입력값을 받는 pydantic 모델에
  필드 19개를 일일이 나열해뒀는데, 그래서 `schema.py`가 나중에 바뀌어도 그 모델은 따라가지
  않고 새 필드값을 조용히 버렸습니다(pydantic이 정의 안 된 키를 무시). 이번 버전은 요청
  바디를 `Dict[str, Any]`로 받고 `COMMON_SCHEMA_FIELDS`를 순회해서 레코드를 만들기 때문에,
  `schema.py`에 필드가 추가/삭제되면 `main.py`는 손댈 필요가 없습니다.
- `extract.py`(watsonx AI 자동채우기)의 프롬프트/필드 설명/타입 매핑에 새 필드 8개를 반영했습니다.
  다만 `view_count`(조회수)와 `last_updated`(최종수정일)는 공고문에 적혀있는 내용이 아니라
  시스템이 관리하는 메타데이터라서 AI 추출/폼 입력 대상에서 제외하고, 저장 시 서버가 자동으로
  채웁니다(view_count는 None, last_updated는 저장 시점 날짜).
- `data/common_policies.json`을 최신 파이프라인 실행 결과(2,869건, 28필드)로 갱신했습니다.

## 재사용한 것

`schema.py` / `validate.py`(source 허용값에 `"manual"` 추가) / `dedup.py`
(`find_duplicates_for_new()` / `record_for_display()` 추가)는 이 폴더의 파이프라인 코드를
그대로 씁니다 - 같은 스키마를 보는 코드가 두 군데로 갈라지지 않도록, 온통청년/지자체 통합
파이프라인이 쓰는 파일을 admin 앱도 import해서 그대로 씁니다.

## 실행 방법

```bash
cd policy_data_modeling
pip install -r requirements.txt

# .env는 이 폴더에 이미 있음 (WATSONX_API_KEY/PROJECT_ID/URL/MODEL_ID).
# 스캔본 PDF·이미지용 vision 모델을 따로 쓰고 싶으면 WATSONX_VISION_MODEL_ID만 추가.

uvicorn main:app --reload --port 8010
```

브라우저에서 http://localhost:8010 접속.

## 플로우

1. (선택) **공고문에서 자동 채우기** — PDF/PNG/JPG 업로드 또는 텍스트 붙여넣기 후 "AI로 채우기".
2. 폼 내용을 확인/수정
3. **검사하기** 클릭 → `/api/check` 호출 (필드 오류/경고 + 중복 의심 정책 + 항목별 비교표)
4. 오류가 없으면 **그래도 저장하기** 버튼이 나타남 → `/api/policies`로 저장
   (`data/manual_policies.json`에 누적)

## 더미 테스트케이스

폼 위 드롭다운에서 중복/비중복/오류/경고 시나리오 9개를 바로 불러와볼 수 있습니다 (`data/test_cases.json`).
이 케이스들이 참조하는 기존 정책(청년 부동산 중개보수 및 이사비 지원사업, 청년주택드림청약통장 등)이
현재 `data/common_policies.json`에도 그대로 있는 것을 확인했습니다.

## 저장된 것을 초기화하고 싶을 때

```bash
rm data/manual_policies.json
```
