### 1) 출처별 파싱 - 온통청년 API / 지자체복지서비스 API 응답을 균일한 레코드 리스트로 추출
# parsers.py

import json
from pathlib import Path
from typing import Any, Dict, List


def parse_ontong(path: str) -> List[Dict[str, Any]]:
    """
    온통청년 API 원본(JSON 배열, 또는 {"result":{"youthPolicyList":[...]}})을
    정책 레코드 리스트로 반환한다. 각 레코드는 원본 필드를 그대로 유지한다.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if "result" in data and "youthPolicyList" in data["result"]:
            return data["result"]["youthPolicyList"]
        if "youthPolicyList" in data:
            return data["youthPolicyList"]

    raise ValueError("지원하지 않는 온통청년 JSON 구조입니다.")


def parse_welfare(path: str) -> List[Dict[str, Any]]:
    """
    지자체복지서비스 상세조회 결과([{"servId":..., "raw":{"wantedDtl":{...}}}, ...])를
    "wantedDtl" 내부 dict만 꺼내서 균일한 레코드 리스트로 반환한다.

    resultCode가 정상(0/"0"/"00")이 아니거나 wantedDtl이 없는 항목은 건너뛰고
    별도로 반환해서 나중에 확인할 수 있게 한다.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    if not isinstance(raw_list, list):
        raise ValueError("지원하지 않는 welfare_detail_raw.json 구조입니다.")

    records: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for entry in raw_list:
        serv_id = entry.get("servId")
        wanted_dtl = (entry.get("raw") or {}).get("wantedDtl")

        if not isinstance(wanted_dtl, dict):
            skipped.append({"servId": serv_id, "reason": "wantedDtl 없음"})
            continue

        result_code = str(wanted_dtl.get("resultCode", "")).strip()
        if result_code not in ("0", "00"):
            skipped.append({
                "servId": serv_id,
                "reason": f"resultCode={result_code}",
                "resultMessage": wanted_dtl.get("resultMessage"),
            })
            continue

        # servId가 wantedDtl 안에 없는 경우를 대비해 상위 entry의 servId로 보정
        if not wanted_dtl.get("servId"):
            wanted_dtl["servId"] = serv_id

        records.append(wanted_dtl)

    return records, skipped


if __name__ == "__main__":
    ontong = parse_ontong("ontongAPI.json")
    welfare, welfare_skipped = parse_welfare("welfare_detail_raw.json")

    print(f"ontong 레코드 수: {len(ontong)}")
    print(f"welfare 레코드 수: {len(welfare)} (스킵 {len(welfare_skipped)}건)")
    if welfare_skipped:
        print("스킵 사례:", welfare_skipped[:5])
