"""
pipeline/summarizer.py

Module tóm tắt văn bản cá nhân hóa theo persona.
Dùng chung cho pipeline chính (main.py) và evaluation (cq_validator_*.py).
"""

import re
import time

from google import genai

from pipeline.community import determine_community
from pipeline.worlds import build_worlds
from pipeline.prompt_builder_2 import build_prompt

SUMMARY_MODEL_NAME = "gemini-3.1-flash-lite"


def retry_generate(func, *args, **kwargs):
    """
    Gọi lại hàm khi gặp lỗi tạm thời từ Gemini API (429 quota, 503 server busy).
    """
    while True:
        try:
            return func(*args, **kwargs)

        except Exception as e:
            msg = str(e)

            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                match = re.search(r"retry in ([0-9.]+)s", msg, re.IGNORECASE)
                wait = float(match.group(1)) + 2 if match else 40
                print(f"\n429 quota. Đợi {wait:.1f}s...")
                time.sleep(wait)
                continue

            elif "503" in msg or "UNAVAILABLE" in msg:
                wait = 20
                print(f"\nServer bận. Đợi {wait}s...")
                time.sleep(wait)
                continue

            raise


def summarize_person(row: dict, text: str, g, client: genai.Client,
                      model_name: str = SUMMARY_MODEL_NAME,
                      extra_instruction: str = "") -> dict:
    community = determine_community(row)
    worlds = build_worlds(row)
    prompt = build_prompt(row, text, g)
    if extra_instruction:
        prompt += f"\n\n[YÊU CẦU BỔ SUNG DO VI PHẠM ĐỘ DÀI]\n{extra_instruction}"
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={"temperature": 0.0},
    )

    summary = response.text.strip()
    return {
        "uuid": row.get("uuid", ""),
        "summary": summary,
        "community": community,
        "worlds": worlds,
        "prompt_len": len(prompt),
    }