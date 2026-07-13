### 7) 중복 탐지 - 지역이 겹치고 제목의 핵심 단어가 비슷한 정책을 "중복 의심" 후보로 묶는다.
# dedup.py
#
# 온통청년과 지자체복지서비스는 ID 체계가 완전히 달라서(plcyNo vs servId) 키로는
# 중복을 못 잡는다. 대신 (1) 지역이 겹치고 (2) 제목이 비슷하면 같은 정책이 두
# 시스템에 각각 등록돼 있을 가능성이 높다고 보고 후보로 묶는다.
#
# 제목 유사도는 문자 단위(difflib)가 아니라 단어(토큰) 단위 Jaccard 유사도를 쓴다.
# 한국 정책명은 "청년", "지원사업", "운영"처럼 흔한 단어를 공유하는 경우가 매우 많아서,
# 문자 단위 유사도는 서로 다른 정책도 유사도가 높게 나오는 오탐이 많았다
# (실측 확인: "[6월 마감]...자격증 취득지원 사업" vs "...청년도전지원사업"이 문자 단위로는
#  1.0이 나오는 등). 흔한 단어를 제외한 단어 집합의 Jaccard 유사도가 훨씬 정확했다.
#
# 절대 자동으로 지우지 않는다 - 중복 "의심" 후보만 별도 파일에 모아서
# 사람이 검토하게 한다 (오탐이 섞여 있을 수 있음).

import re
from typing import Any, Dict, List


TITLE_SIMILARITY_THRESHOLD = 0.34

_BRACKET_PAT = re.compile(r"[\[\(【].*?[\]\)】]")
_NON_WORD_PAT = re.compile(r"[^\w가-힣\s]")

# 정책명에 너무 흔하게 등장해서 변별력이 없는 단어들.
TITLE_STOPWORDS = {
    "지원사업", "지원", "사업", "운영", "청년", "모집", "프로그램", "서비스",
    "지급", "제공", "활동", "센터", "위한", "지원금", "참여", "대상", "추진",
    "조성", "관련", "안내",
}


def normalize_title(title: str) -> str:
    title = title or ""
    title = _BRACKET_PAT.sub(" ", title)
    title = _NON_WORD_PAT.sub(" ", title)
    return title.strip()


def _title_tokens(title: str) -> set:
    normalized = normalize_title(title)
    return {
        w for w in normalized.split()
        if w and w not in TITLE_STOPWORDS and len(w) > 1
    }


def title_similarity(title_a: str, title_b: str) -> float:
    """
    흔한 단어를 제외한 단어 집합의 Jaccard 유사도 (교집합 / 합집합).
    """
    tokens_a = _title_tokens(title_a)
    tokens_b = _title_tokens(title_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _provinces_of(region_names: List[str]) -> set:
    provinces = set()
    for name in region_names or []:
        if name == "전국":
            provinces.add("__ALL__")
            continue
        provinces.add(name.split(" ")[0])
    return provinces


def regions_overlap(region_names_a: List[str], region_names_b: List[str]) -> bool:
    provinces_a = _provinces_of(region_names_a)
    provinces_b = _provinces_of(region_names_b)

    if "__ALL__" in provinces_a or "__ALL__" in provinces_b:
        return True

    return bool(provinces_a & provinces_b)


def find_duplicate_candidates(
    records: List[Dict[str, Any]],
    threshold: float = TITLE_SIMILARITY_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    지역이 겹치고 제목 단어 유사도가 threshold 이상인 레코드 쌍을 찾는다.
    지역(시도) 단위로 블로킹해서 비교 횟수를 줄인다.
    같은 (source, source_id) 레코드끼리는 비교하지 않는다.
    """
    by_province: Dict[str, List[int]] = {}
    for idx, record in enumerate(records):
        provinces = _provinces_of(record.get("region_names") or [])
        if not provinces:
            provinces = {"__NONE__"}
        for p in provinces:
            by_province.setdefault(p, []).append(idx)

    all_indices = list(range(len(records)))

    candidates = []
    seen_pairs = set()

    for province, indices in by_province.items():
        compare_pool = all_indices if province == "__ALL__" else indices

        for i in indices:
            for j in compare_pool:
                if j <= i:
                    continue

                pair_key = (i, j)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                rec_a, rec_b = records[i], records[j]

                if rec_a.get("source") == rec_b.get("source") and rec_a.get("source_id") == rec_b.get("source_id"):
                    continue

                if not regions_overlap(rec_a.get("region_names"), rec_b.get("region_names")):
                    continue

                sim = title_similarity(rec_a.get("title", ""), rec_b.get("title", ""))
                if sim >= threshold:
                    candidates.append({
                        "similarity": round(sim, 3),
                        "a": {
                            "source": rec_a.get("source"),
                            "source_id": rec_a.get("source_id"),
                            "title": rec_a.get("title"),
                            "region_names": rec_a.get("region_names"),
                            "agency": rec_a.get("agency"),
                        },
                        "b": {
                            "source": rec_b.get("source"),
                            "source_id": rec_b.get("source_id"),
                            "title": rec_b.get("title"),
                            "region_names": rec_b.get("region_names"),
                            "agency": rec_b.get("agency"),
                        },
                    })

    candidates.sort(key=lambda c: -c["similarity"])
    return candidates
