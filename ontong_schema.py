### 2) 스키마 정의 - 온통청년 API의 실제 응답 필드(60개, 실측 확인)를 그대로 통합 스키마로 채택
# ontong_schema.py
#
# [브랜치 변경] 기존에는 두 API의 개념을 합쳐 새 공통 스키마를 설계했지만(과거 버전은
# _archive_common_schema_v1/에 보존), 이 버전은 온통청년 API 필드 구조를 "그대로" 정답
# 스키마로 삼고 지자체복지서비스 데이터를 여기에 맞춰 변환한다.
#
# 설계 원칙
# ---------
# - 온통청년 레코드는 원본 그대로 통과시킨다(필드명/코드값 변형 없음).
# - 지자체복지서비스 레코드는 개념이 명확히 대응되는 필드만 채우고, 대응이 불확실한
#   "구조화된 코드" 필드(jobCd/schoolCd/mrgSttsCd/sbizCd/plcyMajorCd/plcyPvsnMthdCd 등)는
#   근거 없이 추측해서 코드를 지어내지 않고 빈 문자열로 둔다(= "확인 불가", 온통청년 자체
#   데이터에서도 빈 문자열이 흔히 쓰이는 표기라 표기 관례상 자연스럽다).
# - 정보가 유실되지 않도록 아래 두 필드를 온통청년 원본 스키마 밖에 추가로 붙인다:
#     source : "ontong" | "welfare"  (두 출처를 나중에 구분하기 위한 최소한의 메타 정보)
#     raw    : 지자체 원본 레코드 전체 (welfare 레코드에만 채움 - 매핑 과정에서 버려진
#              정보를 역추적할 수 있도록. ontong 레코드는 이미 그 자체가 raw이므로 None)
#
# 실측으로 확인한 60개 필드 목록 (ontongAPI.json 전체 2,633건 키의 합집합)

ONTONG_SCHEMA_FIELDS = [
    "plcyNo", "plcyNm", "plcyKywdNm", "plcyExplnCn", "lclsfNm", "mclsfNm", "plcyPvsnMthdCd",
    "pvsnInstGroupCd", "sprvsnInstCd", "sprvsnInstCdNm", "sprvsnInstPicNm",
    "operInstCd", "operInstCdNm", "operInstPicNm",
    "sprtTrgtAgeLmtYn", "sprtTrgtMinAge", "sprtTrgtMaxAge",
    "mrgSttsCd", "earnCndSeCd", "earnMinAmt", "earnMaxAmt", "earnEtcCn",
    "addAplyQlfcCndCn", "ptcpPrpTrgtCn", "jobCd", "schoolCd", "plcyMajorCd", "sbizCd",
    "aplyPrdSeCd", "aplyYmd", "bizPrdSeCd", "bizPrdBgngYmd", "bizPrdEndYmd", "bizPrdEtcCn",
    "plcySprtCn", "sprtSclCnt", "sprtSclLmtYn", "sprtArvlSeqYn",
    "plcyAplyMthdCn", "srngMthdCn", "sbmsnDcmntCn",
    "aplyUrlAddr", "refUrlAddr1", "refUrlAddr2",
    "zipCd",
    "rgtrInstCd", "rgtrInstCdNm", "rgtrUpInstCd", "rgtrUpInstCdNm",
    "rgtrHghrkInstCd", "rgtrHghrkInstCdNm",
    "plcyAprvSttsCd", "frstRegDt", "lastMdfcnDt", "inqCnt",
    "bscPlanCycl", "bscPlanAsmtNo", "bscPlanFcsAsmtNo", "bscPlanPlcyWayNo",
    "etcMttrCn",
]

# 두 출처를 합칠 때 최소한의 추적을 위해 덧붙이는 메타 필드 (온통청년 원본엔 없음)
META_FIELDS = ["source", "raw"]

UNIFIED_SCHEMA_FIELDS = ONTONG_SCHEMA_FIELDS + META_FIELDS


def new_ontong_record(**kwargs) -> dict:
    """
    온통청년 스키마 기본값으로 dict를 만들고 kwargs로 덮어쓴다.
    온통청년 원본 데이터 자체가 "정보 없음"을 빈 문자열("")로 표기하는 경우가
    대부분이라(operInstCd, rgtrUpInstCd 등 실측 확인), 기본값도 그 관례를 따른다.
    """
    record = {field: "" for field in ONTONG_SCHEMA_FIELDS}
    record["source"] = ""
    record["raw"] = None
    record.update(kwargs)
    return record
