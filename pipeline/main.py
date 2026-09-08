"""
pipeline/main.py
"""

import argparse
import json
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from google import genai

load_dotenv()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipeline.community import determine_community
from pipeline.worlds import build_worlds
from pipeline.content_classifier import classify_content
from pipeline.ontology_context import load_graph, build_ontology_context
from pipeline.prompt_builder import build_prompt, build_neutral_prompt, build_brief_prompt
from pipeline.summarizer import summarize_person, retry_generate, SUMMARY_MODEL_NAME
from pipeline.text_store import load_custom_texts
from pipeline.relevance import score_text_relevance

DATA_CSV = os.path.join(PROJECT_ROOT, "data", "sample50.csv")
TTL_PATH = os.path.join(PROJECT_ROOT, "ontology", "persona_analysis_2_1.ttl")
TEXTS_PATH = os.path.join(PROJECT_ROOT, "evaluation", "cq_test_cases.json")
CUSTOM_TEXT_STORE = os.path.join(PROJECT_ROOT, "document", "text.txt")

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
DIR_PROFILES = os.path.join(OUTPUT_DIR, "profiles")
DIR_INFERENCES = os.path.join(OUTPUT_DIR, "inferences")
DIR_GUIDE = os.path.join(OUTPUT_DIR, "summarization_guide")
DIR_GENERAL = os.path.join(OUTPUT_DIR, "summaries", "general")
DIR_SPECIFIC = os.path.join(OUTPUT_DIR, "summaries", "specific")

for d in [DIR_PROFILES, DIR_INFERENCES, DIR_GUIDE, DIR_GENERAL, DIR_SPECIFIC]:
    os.makedirs(d, exist_ok=True)

MAX_LENGTH_RETRIES = 2


def load_texts() -> dict:
    with open(TEXTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["texts"]


def save_json(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_text(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def check_length(summary: str, source: str, ratio: float = 0.7) -> tuple[bool, int, int]:
    src_words = len(source.split())
    sum_words = len(summary.split())
    return sum_words <= ratio * src_words, sum_words, int(ratio * src_words)


def generate_with_length_limit(generate_fn, source_text: str, base_kwargs: dict,
                                 prompt_key: str, ratio: float = 0.7):
    attempt = 0
    feedback = ""
    last_summary = None
    last_count = None
    max_words = int(ratio * len(source_text.split()))

    while attempt <= MAX_LENGTH_RETRIES:
        kwargs = dict(base_kwargs)
        if feedback:
            kwargs[prompt_key] = kwargs[prompt_key] + f"\n\n[YÊU CẦU BỔ SUNG DO VI PHẠM ĐỘ DÀI]\n{feedback}"

        response = retry_generate(generate_fn, **kwargs)
        summary = response.text.strip() if hasattr(response, "text") else response["summary"].strip()

        ok, sum_words, max_words = check_length(summary, source_text, ratio)
        last_summary, last_count = summary, sum_words

        if ok:
            return summary, {"length_ok": True, "words": sum_words, "max_words": max_words, "attempts": attempt + 1}

        feedback = (f"Bản tóm tắt trước có {sum_words} từ, vượt quá giới hạn {max_words} từ "
                    f"(tối đa {int(ratio*100)}% số từ bản gốc). Hãy viết lại NGẮN HƠN, "
                    f"cắt bớt chi tiết phụ, không thêm câu mới.")
        attempt += 1

    return last_summary, {"length_ok": False, "words": last_count, "max_words": max_words, "attempts": attempt}


def generate_specific_with_length_limit(row, text, g, client, ratio: float = 0.7):
    attempt = 0
    feedback = ""
    result = None
    sum_words = None
    max_words = int(ratio * len(text.split()))

    while attempt <= MAX_LENGTH_RETRIES:
        result = retry_generate(summarize_person, row, text, g, client, extra_instruction=feedback)
        ok, sum_words, max_words = check_length(result["summary"], text, ratio)

        if ok:
            return result, {"length_ok": True, "words": sum_words, "max_words": max_words, "attempts": attempt + 1}

        feedback = (f"Bản tóm tắt trước có {sum_words} từ, vượt quá giới hạn {max_words} từ. "
                    f"Viết lại ngắn hơn, cắt chi tiết phụ, không thêm câu mới.")
        attempt += 1

    return result, {"length_ok": False, "words": sum_words, "max_words": max_words, "attempts": attempt}


def generate_brief_mention(text: str, client) -> str:
    prompt = build_brief_prompt(text)
    response = retry_generate(
        client.models.generate_content,
        model=SUMMARY_MODEL_NAME,
        contents=prompt,
        config={"temperature": 0.0},
    )
    return response.text.strip()


def build_combined_output(primary_id, primary_summary, others_meta) -> str:
    lines = [f"[Nội dung chính — {primary_id}]", primary_summary, ""]
    if others_meta:
        lines.append("[Nội dung khác được nhắc qua]")
        for text_id, brief in others_meta:
            lines.append(f"- {text_id}: {brief}")
    return "\n".join(lines)


def process_multi_texts(row: dict, texts: dict, g, client) -> dict:
    uuid = row.get("uuid", f"row_{row.get('index', 'unknown')}")

    community = determine_community(row)
    worlds = build_worlds(row)

    save_json(os.path.join(DIR_PROFILES, f"{uuid}.json"),
              {"uuid": uuid, "raw_fields": row, "community": community})
    save_json(os.path.join(DIR_INFERENCES, f"{uuid}.json"), worlds)

    scored = []
    for text_id, text in texts.items():
        content_meta = classify_content(text)
        score = score_text_relevance(row, community, content_meta)
        scored.append({"text_id": text_id, "text": text,
                        "content_meta": content_meta, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)

    primary = scored[0]
    others = scored[1:]

    general_meta_all = {}
    for item in scored:
        neutral_prompt = build_neutral_prompt(item["text"])
        g_summary, g_meta = generate_with_length_limit(
            client.models.generate_content,
            source_text=item["text"],
            base_kwargs={"model": SUMMARY_MODEL_NAME, "contents": neutral_prompt,
                         "config": {"temperature": 0.0}},
            prompt_key="contents",
        )
        save_text(os.path.join(DIR_GENERAL, f"{uuid}_{item['text_id']}.txt"), g_summary)
        general_meta_all[item["text_id"]] = g_meta

    primary_result, primary_meta = generate_specific_with_length_limit(row, primary["text"], g, client)

    others_meta = []
    for item in others:
        brief = generate_brief_mention(item["text"], client)
        others_meta.append((item["text_id"], brief))

    combined = build_combined_output(primary["text_id"], primary_result["summary"], others_meta)
    save_text(os.path.join(DIR_SPECIFIC, f"{uuid}_combined.txt"), combined)

    guide = {
        "uuid": uuid,
        "mode": "multi_text",
        "ranking": [{"text_id": s["text_id"], "score": s["score"],
                     "content_classification": s["content_meta"]} for s in scored],
        "primary_text_id": primary["text_id"],
        "community_used": community,
        "length_check": {"specific_primary": primary_meta, "general": general_meta_all},
    }
    save_json(os.path.join(DIR_GUIDE, f"{uuid}_multi.json"), guide)

    status = "OK"
    if not primary_meta["length_ok"]:
        status = "OK_LENGTH_WARNING"

    return {"uuid": uuid, "mode": "multi_text",
            "primary_text_id": primary["text_id"], "status": status}


def process_one(row: dict, text: str, text_id: str, g, client: genai.Client) -> dict:
    uuid = row.get("uuid", f"row_{row.get('index', 'unknown')}")

    community = determine_community(row)
    worlds = build_worlds(row)
    content_meta = classify_content(text)

    profile = {
        "uuid": uuid,
        "raw_fields": row,
        "community": community,
    }
    save_json(os.path.join(DIR_PROFILES, f"{uuid}.json"), profile)
    save_json(os.path.join(DIR_INFERENCES, f"{uuid}.json"), worlds)

    guide = {
        "uuid": uuid,
        "text_id": text_id,
        "content_classification": content_meta,
        "community_used": community,
    }

    neutral_prompt = build_neutral_prompt(text)
    general_summary, general_meta = generate_with_length_limit(
        client.models.generate_content,
        source_text=text,
        base_kwargs={"model": SUMMARY_MODEL_NAME, "contents": neutral_prompt, "config": {"temperature": 0.0}},
        prompt_key="contents",
    )
    save_text(os.path.join(DIR_GENERAL, f"{uuid}_{text_id}.txt"), general_summary)

    result, specific_meta = generate_specific_with_length_limit(row, text, g, client)
    save_text(os.path.join(DIR_SPECIFIC, f"{uuid}_{text_id}.txt"), result["summary"])

    guide["length_check"] = {"general": general_meta, "specific": specific_meta}
    save_json(os.path.join(DIR_GUIDE, f"{uuid}_{text_id}.json"), guide)

    status = "OK"
    if not general_meta["length_ok"] or not specific_meta["length_ok"]:
        status = "OK_LENGTH_WARNING"

    return {"uuid": uuid, "text_id": text_id, "status": status}


def run(row_indices, text_ids=None, api_key=None, use_custom=False):
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Chưa set GEMINI_API_KEY. Chạy: export GEMINI_API_KEY=your_key")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    df = pd.read_csv(DATA_CSV)
    g = load_graph(TTL_PATH)

    results = []

    if use_custom:
        custom_texts = load_custom_texts(CUSTOM_TEXT_STORE)
        if not custom_texts:
            print(f"Không có văn bản nào trong {CUSTOM_TEXT_STORE}")
            sys.exit(1)
        for row_idx in row_indices:
            row = df.iloc[row_idx].to_dict()
            print(f"Đang xử lý (multi-text): row={row_idx}, {len(custom_texts)} văn bản...")
            try:
                res = process_multi_texts(row, custom_texts, g, client)
                results.append(res)
                print(f"  => {res['status']} (chính: {res['primary_text_id']})")
            except Exception as e:
                print(f"  !!! LỖI: {e}")
                results.append({"uuid": row.get("uuid", f"row_{row_idx}"), "status": "ERROR", "error": str(e)})
        return results

    texts = load_texts()
    for row_idx in row_indices:
        row = df.iloc[row_idx].to_dict()
        for text_id in text_ids:
            if text_id not in texts:
                print(f"  !!! Bỏ qua: text_id '{text_id}' không tồn tại trong {TEXTS_PATH}")
                continue
            text = texts[text_id]
            print(f"Đang xử lý: row={row_idx}, text_id={text_id}...")
            try:
                res = process_one(row, text, text_id, g, client)
                results.append(res)
                print(f"  => {res['status']}")
            except Exception as e:
                print(f"  !!! LỖI: {e}")
                results.append({
                    "uuid": row.get("uuid", f"row_{row_idx}"),
                    "text_id": text_id,
                    "status": "ERROR",
                    "error": str(e),
                })

    return results


def main():
    parser = argparse.ArgumentParser(description="Chạy pipeline sản xuất Personas end-to-end.")
    parser.add_argument("--rows", nargs="*", type=int, default=None,
                         help="Chỉ số dòng (0-indexed) trong sample50.csv cần xử lý")
    parser.add_argument("--all-rows", action="store_true",
                         help="Xử lý toàn bộ 50 dòng trong sample50.csv")
    parser.add_argument("--texts", nargs="+", default=None,
                         help="Danh sách text_id trong cq_test_cases.json (dùng cho evaluation)")
    parser.add_argument("--custom-texts", action="store_true",
                         help="Dùng nhiều văn bản tự nhập trong document/text.txt")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    if not args.texts and not args.custom_texts:
        print("Cần chỉ định --texts hoặc --custom-texts")
        sys.exit(1)

    df = pd.read_csv(DATA_CSV)
    if args.all_rows:
        row_indices = list(range(len(df)))
    elif args.rows:
        row_indices = args.rows
    else:
        print("Cần chỉ định --rows hoặc --all-rows")
        sys.exit(1)

    results = run(row_indices, text_ids=args.texts, api_key=args.api_key, use_custom=args.custom_texts)

    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_warn = sum(1 for r in results if r["status"] == "OK_LENGTH_WARNING")
    n_err = sum(1 for r in results if r["status"] == "ERROR")
    print(f"\nHoàn tất: {n_ok} OK, {n_warn} cảnh báo độ dài, {n_err} lỗi. Kết quả tại: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()