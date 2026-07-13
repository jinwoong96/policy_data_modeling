# 정책 관리자 수동추가 - 로컬 테스트앱

관리자가 정책을 수동으로 추가할 때, DB에 반영하기 전에 **필드 검증 + 중복탐지 + AI 자동채우기**가
어떻게 동작하는지 화면에서 직접 클릭해보기 위한 독립 실행 앱입니다.
bene_backend/bene_frontend와는 별개로 로컬에서만 동작합니다.

## 무엇을 재사용했나

`policy_data_modeling`의 아래 3개 파일을 그대로(또는 최소 수정) 가져왔습니다.

- `schema.py` — 그대로. 폼 필드, AI 추출 프롬프트가 모두 `COMMON_SCHEMA_FIELDS` 기준으로 생성됩니다.
- `validate.py` — `source` 허용값에 `"manual"`만 추가.
- `dedup.py` — `find_duplicates_for_new()` / `record_for_display()` 두 함수 추가
  (기존 `find_duplicate_candidates()`는 배치 전체 pairwise 비교용이라,
  "신규 입력 1건 vs 기존 DB 전체" 비교 + 컬럼별 비교 화면용 전체필드 반환 버전을 별도로 만들었습니다).

새로 추가한 `extract.py`는 공고문(PDF/이미지/텍스트)을 **watsonx.ai**로 읽어서
`COMMON_SCHEMA_FIELDS`에 맞는 JSON 초안을 만듭니다. **AI는 폼을 채워줄 뿐, 저장은 대신하지 않습니다** —
추출된 값도 여전히 `validate_record()` + `find_duplicates_for_new()`를 통과해야 저장 버튼이 활성화됩니다.

watsonx.ai는 Claude와 달리 PDF를 통째로 읽지 못해서, 파일 종류에 따라 경로가 갈립니다.

- **텍스트만 붙여넣은 경우** → 텍스트 모델(`WATSONX_MODEL_ID`)로 바로
- **텍스트 레이어가 있는 PDF** (대부분의 관공서 공고 PDF) → `pypdf`로 텍스트만 뽑아서 텍스트 모델로
- **텍스트 레이어가 거의 없는 PDF(스캔본)** → `PyMuPDF`로 페이지를 이미지로 렌더링해서 vision 모델(`WATSONX_VISION_MODEL_ID`)로
- **이미지 업로드(PNG/JPG)** → 바로 vision 모델로

이 라우팅은 `extract.py`의 `extract_policy_fields()` 안에서 자동으로 처리되고,
`main.py`는 이 함수 시그니처만 알면 되니 provider를 바꿔도(예: 다시 Claude로) `main.py`는 손댈 필요 없습니다.

"기존 DB"는 아직 RDS에 안 들어간 상태라, `output/common_policies.json`
(2,869건)을 그대로 `data/common_policies.json`에 복사해 서버 시작 시
메모리에 로드하는 것으로 대신했습니다. 실제 서비스에 붙일 때는
`load_existing()` 부분만 RDS `policy` 테이블 조회로 바꾸면 됩니다.

## 실행 방법

```bash
cd admin_test_app
pip install -r requirements.txt

cp .env.example .env
# .env 파일을 열어서 아래 값을 채워넣기
#   WATSONX_API_KEY=...
#   WATSONX_PROJECT_ID=...
#   WATSONX_URL=https://us-south.ml.cloud.ibm.com   (리전 맞게)
#   WATSONX_MODEL_ID=...        (bene_ai에서 쓰는 모델 있으면 그걸로)
#   WATSONX_VISION_MODEL_ID=... (스캔본/이미지 공고문용, 기본값 그대로 써도 됨)

uvicorn main:app --reload --port 8010
```

브라우저에서 http://localhost:8010 접속.

`.env` 파일은 서버가 켜질 때 `extract.py`가 자동으로 읽어서 환경변수로 채워줍니다(`python-dotenv`).
껐다 켤 때마다 터미널에 `export`를 다시 칠 필요 없이, 파일에 한 번만 적어두면 됩니다.
`.gitignore`에 이미 `.env`가 들어있으니 실수로 커밋될 걱정은 안 하셔도 됩니다.

이 값들이 없어도 AI 자동채우기만 안 되고 나머지 기능(폼 직접입력, 검사, 중복탐지, 비교표, 저장)은
그대로 다 동작합니다.

## 플로우

1. (선택) **공고문에서 자동 채우기** — PDF/PNG/JPG 업로드 또는 텍스트 붙여넣기 후 "AI로 채우기".
   AI가 채운 필드는 라벨 옆에 `AI` 배지가 붙고, 못 찾은 항목은 상태 메시지에 나열됩니다.
   → 이 상태에서 저장되는 건 아무것도 없습니다. 반드시 사람이 확인 후 아래 단계를 거쳐야 합니다.
2. 폼 내용을 확인/수정
3. **검사하기** 클릭 → `/api/check` 호출
   - `validate_record()` 결과: 필드 오류(빨강) / 경고(노랑)
   - `find_duplicates_for_new()` 결과: 지역 겹치고 제목 유사한 기존 정책이 카드로 표시되고,
     카드마다 "항목별 비교 보기"를 누르면 신규입력 vs 기존정책 컬럼별 비교표(다른 값만 강조)가 펼쳐짐
4. 오류가 없으면 **그래도 저장하기** 버튼이 나타남 → `/api/policies`로 저장
   (`data/manual_policies.json`에 누적, 다음 검사 때부터 비교 대상에도 포함됨)

## 더미 테스트케이스

폼 위 드롭다운에서 중복/비중복/오류/경고 시나리오 9개를 바로 불러와볼 수 있습니다 (`data/test_cases.json`).

## 저장된 것을 초기화하고 싶을 때

```bash
rm data/manual_policies.json
```
