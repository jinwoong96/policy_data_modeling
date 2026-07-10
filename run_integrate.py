### 전체 파이프라인 오케스트레이터 - 1~7단계를 순서대로 실행
# run_integrate.py

import json
from pathlib import Path

from parsers import parse_ontong, parse_welfare
from adapters import ontong_to_common, welfare_to_common
from standardize import RegionStandardizer
from validate import split_valid_invalid
from dedup import find_duplicate_candidates


ONTONG_FILE = "ontongAPI.json"
WELFARE_FILE = "welfare_detail_raw.json"
ZIPCD_MAPPING_FILE = "zipcd_mapping.csv"

OUTPUT_DIR = "output"
COMMON_FILE = f"{OUTPUT_DIR}/common_policies.json"
INVALID_FILE = f"{OUTPUT_DIR}/invalid_records.json"
DUPLICATE_CANDIDATES_FILE = f"{OUTPUT_DIR}/duplicate_candidates.json"
PARSE_SKIPPED_FILE = f"{OUTPUT_DIR}/welfare_parse_skipped.json"

DUPLICATE_SIMILARITY_THRESHOLD = 0.34


def save_json(path: str, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    # 1) 출처별 파싱
    print("[1/7] 출처별 파싱...")
    ontong_records = parse_ontong(ONTONG_FILE)
    welfare_records, welfare_skipped = parse_welfare(WELFARE_FILE)
    print(f"  ontong: {len(ontong_records)}건, welfare: {len(welfare_records)}건 (스킵 {len(welfare_skipped)}건)")
    if welfare_skipped:
        save_json(PARSE_SKIPPED_FILE, welfare_skipped)

    # 2) 공통 스키마는 schema.py에 정의되어 있음 (실행 시 별도 동작 없음)

    # 3) 필드 매핑 (어댑터) - 4) 값 표준화 - 5) 조건 추출은 adapters.py 안에서 함께 처리됨
    print("[2-5/7] 공통 스키마 변환 (매핑 + 표준화 + 조건추출)...")
    region_std = RegionStandardizer(ZIPCD_MAPPING_FILE)

    common_records = []
    for r in ontong_records:
        common_records.append(ontong_to_common(r, region_std))
    for r in welfare_records:
        common_records.append(welfare_to_common(r, region_std))
    print(f"  통합 레코드 수: {len(common_records)}건")

    # 6) 검증 및 오류 분리
    print("[6/7] 검증 및 오류 분리...")
    valid_records, invalid_records = split_valid_invalid(common_records)
    print(f"  valid: {len(valid_records)}건, invalid: {len(invalid_records)}건")

    # 7) 중복 탐지 (삭제하지 않고 별도 파일로 분리)
    print("[7/7] 중복 후보 탐지...")
    duplicate_candidates = find_duplicate_candidates(valid_records, threshold=DUPLICATE_SIMILARITY_THRESHOLD)
    print(f"  중복 의심 쌍: {len(duplicate_candidates)}건 (threshold={DUPLICATE_SIMILARITY_THRESHOLD})")

    save_json(COMMON_FILE, valid_records)
    save_json(INVALID_FILE, invalid_records)
    save_json(DUPLICATE_CANDIDATES_FILE, duplicate_candidates)

    print("\n=== 완료 ===")
    print(f"통합 결과: {COMMON_FILE} ({len(valid_records)}건)")
    print(f"검증 실패: {INVALID_FILE} ({len(invalid_records)}건)")
    print(f"중복 의심(삭제 안 함, 검토용): {DUPLICATE_CANDIDATES_FILE} ({len(duplicate_candidates)}쌍)")


if __name__ == "__main__":
    main()
