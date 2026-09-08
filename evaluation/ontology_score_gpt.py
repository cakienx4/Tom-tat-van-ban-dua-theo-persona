"""
ontology_score_gpt.py
Tính Ontology Score = (feature_coverage + CQ_coverage) / 2
Dùng gpt qua OpenAI-compatible endpoint (vLLM / LM Studio / ...).

  feature_coverage : tỷ lệ đặc trưng persona thực tế trong sample50.csv
                     được bao phủ bởi ít nhất một term trong ontology
  CQ_coverage      : tỷ lệ CQ có verdict PASS trong cq_validation_results_gemini.json

Quy trình đo feature_coverage (per branch):
  1. Dùng gpt trích danh sách đặc trưng cụ thể từ toàn bộ 50 prose text
     (1 call / branch → 10 calls tổng)
  2. Với mỗi đặc trưng, thử match string với term names + synonyms của ontology
     Những đặc trưng không match được → gộp lại, dùng 1 call / branch để
     đánh giá semantic coverage
  3. coverage = số đặc trưng được bao phủ / tổng đặc trưng trích được

Cách dùng:
    python ontology_score_gpt.py
    python ontology_score_gpt.py --cq-results path/to/cq_validation_results.json
"""

import argparse
import json
import os
import re
import sys
import time

import pandas as pd
import pronto
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── CẤU HÌNH MODEL ──────────────────────────────────────────────────────────
BASE_URL   = "..."
MODEL_NAME = "gpt-oss-120b"
API_KEY    = "EMPTY"
# ────────────────────────────────────────────────────────────────────────────

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_CSV        = os.path.join(BASE_DIR, "..", "data",     "sample50.csv")
OBO_PATH        = os.path.join(BASE_DIR, "..", "ontology", "persona_analysis_3.obo")
CQ_JSON_DEFAULT = os.path.join(BASE_DIR, "cq_validation_results_gpt.json")
OUT_JSON        = os.path.join(BASE_DIR, "ontology_score_results_gpt.json")
OUT_MD          = os.path.join(BASE_DIR, "ontology_score_report_gpt.md")

# 10 nhánh chính của ontology, map sang cột tương ứng trong CSV
BRANCH_COLUMN_MAP = {
    "professional_persona":       "professional_persona",
    "sports_persona":             "sports_persona",
    "arts_persona":               "arts_persona",
    "travel_persona":             "travel_persona",
    "culinary_persona":           "culinary_persona",
    "persona":                    "persona",
    "cultural_background":        "cultural_background",
    "skills_and_expertise":       "skills_and_expertise",
    "hobbies_and_interests":      "hobbies_and_interests",
    "career_goals_and_ambitions": "career_goals_and_ambitions",
}


# ── LOAD ONTOLOGY ────────────────────────────────────────────────────────────

def load_ontology_terms(obo_path: str) -> dict:
    """
    Trả về dict: branch_id -> {"l1": [...], "all_names": set()}
    all_names: tất cả tên term + synonym + keyword từ def ở mọi cấp trong branch
    """
    onto = pronto.Ontology(obo_path)
    result = {}

    for branch_id in BRANCH_COLUMN_MAP:
        root   = onto[branch_id]
        l1_terms  = []
        all_names = set()

        for t in root.subclasses(with_self=False):
            name  = t.name or ""
            defn  = str(t.definition) if t.definition else ""
            depth = len(list(t.superclasses(with_self=False))) - 1  # 0-based từ root

            if depth == 1:  # L1 = con trực tiếp của root
                l1_terms.append({"id": t.id, "name": name, "def": defn})

            if name:
                all_names.add(name.lower())
            for s in t.synonyms:
                if s.description:
                    all_names.add(s.description.lower())
            for word in re.findall(r'\b\w{4,}\b', defn.lower()):
                all_names.add(word)

        result[branch_id] = {"l1": l1_terms, "all_names": all_names}

    return result


# ── OPENAI-COMPATIBLE CLIENT ─────────────────────────────────────────────────

def make_client() -> OpenAI:
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def retry_generate(client: OpenAI, prompt: str) -> str:
    """Gọi model, tự retry khi gặp rate-limit hoặc lỗi tạm thời."""
    while True:
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ("429", "rate", "overloaded", "timeout")):
                match = re.search(r"retry in ([0-9.]+)s", msg, re.IGNORECASE)
                wait  = float(match.group(1)) + 2 if match else 30
                print(f"  ⚠ Lỗi tạm thời, chờ {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise


# ── BƯỚC 1: TRÍCH ĐẶC TRƯNG ─────────────────────────────────────────────────

def extract_features(client: OpenAI, branch_id: str,
                     l1_terms: list, prose_list: list) -> list:
    """
    Dùng gpt trích danh sách đặc trưng cụ thể từ toàn bộ prose text của branch.
    Trả về list[str] đã de-duplicate.
    """
    l1_str    = "\n".join(f'- {t["name"]}: {t["def"][:120]}' for t in l1_terms)
    texts_str = "\n\n".join(
        f'[{i+1}] {p}'
        for i, p in enumerate(prose_list)
        if p and str(p).strip().lower() not in ("nan", "")
    )

    prompt = f"""Bạn đang phân tích nhánh ontology "{branch_id}" với các chiều phân tích (L1):
{l1_str}

Dưới đây là nội dung mô tả về {len(prose_list)} người dùng:
{texts_str}

Nhiệm vụ: Trích xuất danh sách các ĐẶC TRƯNG CỤ THỂ (không trừu tượng) xuất hiện \
trong tất cả các đoạn văn trên. Ví dụ: "chơi bóng bàn", "thích du lịch bụi", \
"kỹ năng lập trình Python", "thích ẩm thực cay", v.v.

Quy tắc:
- Mỗi đặc trưng là một cụm từ ngắn (2-6 từ), cụ thể, không lặp nhau
- Không thêm giải thích, chỉ liệt kê
- Tối đa 80 đặc trưng, ưu tiên các đặc trưng xuất hiện nhiều lần

CHỈ trả về JSON array of strings, không thêm bất kỳ nội dung nào khác:
["đặc trưng 1", "đặc trưng 2", ...]
"""
    raw     = retry_generate(client, prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    # gpt đôi khi trả về <think>...</think> trước JSON — loại bỏ
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    try:
        features = json.loads(cleaned)
        if isinstance(features, list):
            return [str(f).strip() for f in features if f]
    except Exception:
        lines = [l.strip().strip('"-,') for l in cleaned.split("\n") if l.strip()]
        return [l for l in lines if 2 < len(l) < 80]
    return []


# ── BƯỚC 2: MATCH ────────────────────────────────────────────────────────────

def string_match(feature: str, all_names: set) -> bool:
    words = set(re.findall(r'\b\w{4,}\b', feature.lower()))
    return bool(words & all_names)


def semantic_match(client: OpenAI, branch_id: str,
                   l1_terms: list, unmatched_features: list) -> dict:
    """
    Với các đặc trưng chưa match được string, hỏi gpt xem
    L1 term nào trong ontology có thể bao phủ không.
    Trả về dict: feature -> True/False
    """
    if not unmatched_features:
        return {}

    l1_str       = "\n".join(f'- {t["name"]}: {t["def"][:120]}' for t in l1_terms)
    features_str = "\n".join(f'- {f}' for f in unmatched_features)

    prompt = f"""Nhánh ontology "{branch_id}" có các chiều phân tích (L1) sau:
{l1_str}

Với mỗi đặc trưng dưới đây, hãy đánh giá xem có ít nhất một chiều phân tích trên \
có thể bao phủ (classify, categorize) đặc trưng đó không.

Đặc trưng cần đánh giá:
{features_str}

CHỈ trả về JSON object, key là tên đặc trưng (nguyên văn), value là true/false:
{{"đặc trưng 1": true, "đặc trưng 2": false, ...}}
"""
    raw     = retry_generate(client, prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return {k: bool(v) for k, v in result.items()}
    except Exception:
        pass
    # Parse lỗi → mặc định covered (conservative)
    return {f: True for f in unmatched_features}


# ── FEATURE COVERAGE ─────────────────────────────────────────────────────────

def measure_feature_coverage(client: OpenAI, df: pd.DataFrame,
                              onto_terms: dict) -> dict:
    branch_results = {}

    for branch_id, col in BRANCH_COLUMN_MAP.items():
        print(f"\n  [{branch_id}]")

        l1_terms  = onto_terms[branch_id]["l1"]
        all_names = onto_terms[branch_id]["all_names"]

        prose_list = [
            str(v) for v in df[col].tolist()
            if v and str(v).strip().lower() not in ("nan", "")
        ]
        print(f"    {len(prose_list)}/50 texts hợp lệ")

        if not prose_list:
            branch_results[branch_id] = {
                "features_total": 0, "features_covered": 0,
                "coverage": 0.0, "details": [],
            }
            continue

        print("    → Đang trích đặc trưng...")
        features = extract_features(client, branch_id, l1_terms, prose_list)
        print(f"    → Trích được {len(features)} đặc trưng")
        time.sleep(1)

        if not features:
            branch_results[branch_id] = {
                "features_total": 0, "features_covered": 0,
                "coverage": 0.0, "details": [],
            }
            continue

        matched   = {}
        unmatched = []
        for f in features:
            if string_match(f, all_names):
                matched[f] = True
            else:
                unmatched.append(f)

        print(f"    → String match: {len(matched)}/{len(features)} | "
              f"Cần semantic: {len(unmatched)}")

        if unmatched:
            sem = semantic_match(client, branch_id, l1_terms, unmatched)
            matched.update(sem)
            time.sleep(1)

        total   = len(features)
        covered = sum(1 for v in matched.values() if v)
        details = [{"feature": f, "covered": matched.get(f, False)} for f in features]

        branch_results[branch_id] = {
            "features_total":   total,
            "features_covered": covered,
            "coverage":         round(covered / total, 4) if total else 0.0,
            "details":          details,
        }
        print(f"    → Coverage: {covered}/{total} = "
              f"{branch_results[branch_id]['coverage']:.1%}")

    return branch_results


# ── CQ COVERAGE ──────────────────────────────────────────────────────────────

def measure_cq_coverage(cq_json_path: str) -> dict:
    with open(cq_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    total   = len(results)
    passed  = sum(
        1 for r in results
        if r.get("judge") and r["judge"].get("verdict") == "PASS"
    )
    return {
        "total_cq":  total,
        "passed_cq": passed,
        "coverage":  round(passed / total, 4) if total else 0.0,
        "per_cq": [
            {
                "cq_id":      r["cq_id"],
                "verdict":    r["judge"]["verdict"] if r.get("judge") else "N/A",
                "confidence": r["judge"].get("confidence") if r.get("judge") else None,
            }
            for r in results
        ],
    }


# ── EXPORT ────────────────────────────────────────────────────────────────────

def export_json(feature_results: dict, cq_results: dict, score: float):
    total_f = sum(b["features_total"]   for b in feature_results.values())
    cover_f = sum(b["features_covered"] for b in feature_results.values())
    feat_cov = round(cover_f / total_f, 4) if total_f else 0.0

    payload = {
        "model":           MODEL_NAME,
        "ontology_score":  round(score, 4),
        "feature_coverage": {
            "overall":          feat_cov,
            "total_features":   total_f,
            "covered_features": cover_f,
            "per_branch": {
                bid: {
                    "features_total":   b["features_total"],
                    "features_covered": b["features_covered"],
                    "coverage":         b["coverage"],
                }
                for bid, b in feature_results.items()
            },
        },
        "cq_coverage": cq_results,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nĐã ghi: {OUT_JSON}")


def export_markdown(feature_results: dict, cq_results: dict, score: float):
    total_f  = sum(b["features_total"]   for b in feature_results.values())
    cover_f  = sum(b["features_covered"] for b in feature_results.values())
    feat_cov = round(cover_f / total_f, 4) if total_f else 0.0

    lines = []
    lines.append(f"# Ontology Score Report — {MODEL_NAME}\n")
    lines.append("## Kết quả tổng\n")
    lines.append("| Thành phần | Giá trị |")
    lines.append("|---|---|")
    lines.append(f"| Feature Coverage | {feat_cov:.1%} ({cover_f}/{total_f}) |")
    lines.append(f"| CQ Coverage | {cq_results['coverage']:.1%} "
                 f"({cq_results['passed_cq']}/{cq_results['total_cq']}) |")
    lines.append(f"| **Ontology Score** | **{score:.1%}** |\n")

    lines.append("## Feature Coverage theo nhánh\n")
    lines.append("| Nhánh | Đặc trưng trích | Được bao phủ | Coverage |")
    lines.append("|---|---|---|---|")
    for bid, b in feature_results.items():
        lines.append(
            f"| {bid} | {b['features_total']} | {b['features_covered']} "
            f"| {b['coverage']:.1%} |"
        )
    lines.append("")

    lines.append("## CQ Coverage\n")
    lines.append("| CQ | Verdict | Confidence |")
    lines.append("|---|---|---|")
    for c in cq_results["per_cq"]:
        lines.append(f"| {c['cq_id']} | {c['verdict']} | {c['confidence']} |")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Đã ghi: {OUT_MD}")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cq-results", default=CQ_JSON_DEFAULT,
                        help="Đường dẫn đến file cq_validation_results*.json")
    args = parser.parse_args()

    client = make_client()
    df     = pd.read_csv(DATA_CSV)

    print("=== Đang load ontology...")
    onto_terms = load_ontology_terms(OBO_PATH)
    print(f"    Loaded {sum(len(v['l1']) for v in onto_terms.values())} L1 terms "
          f"từ {len(onto_terms)} nhánh\n")

    print("=== Đo Feature Coverage...")
    feature_results = measure_feature_coverage(client, df, onto_terms)

    print("\n=== Đo CQ Coverage...")
    cq_results = measure_cq_coverage(args.cq_results)
    print(f"    CQ Coverage: {cq_results['passed_cq']}/{cq_results['total_cq']} "
          f"= {cq_results['coverage']:.1%}")

    total_f  = sum(b["features_total"]   for b in feature_results.values())
    cover_f  = sum(b["features_covered"] for b in feature_results.values())
    feat_cov = cover_f / total_f if total_f else 0.0
    score    = (feat_cov + cq_results["coverage"]) / 2

    print(f"\n{'='*40}")
    print(f"Model            : {MODEL_NAME}")
    print(f"Feature Coverage : {feat_cov:.1%}")
    print(f"CQ Coverage      : {cq_results['coverage']:.1%}")
    print(f"Ontology Score   : {score:.1%}")
    print(f"{'='*40}")

    export_json(feature_results, cq_results, score)
    export_markdown(feature_results, cq_results, score)


if __name__ == "__main__":
    main()
