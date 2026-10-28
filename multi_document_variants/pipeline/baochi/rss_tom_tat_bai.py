"""
Tầng 1 của pipeline cá nhân hóa RSS báo chí: tóm tắt/cô đọng TỪNG bài báo riêng lẻ,
KHÔNG cá nhân hóa theo persona (persona-agnostic) — vì 1 bài báo có thể được nhiều
persona quan tâm, tóm tắt 1 lần rồi dùng lại cho tất cả, tránh gọi LLM lặp lại.
"""

import hashlib
import json
from pathlib import Path

from pipeline.utils import retry_generate_async, OSS_MODEL_NAME

TOM_TAT_BAI_MAX_TOKENS = 512
TOM_TAT_BAI_MAX_KY_TU_NOI_DUNG = 6000

CACHE_TOM_TAT_BAI_DIR = Path("output/bao_chi/rss_tom_tat_bai")


def _cache_key_bai(bai: dict) -> str:
    link = bai.get("link", "")
    return hashlib.md5(link.encode("utf-8")).hexdigest()[:16]


def _cache_path_bai(bai: dict) -> Path:
    return CACHE_TOM_TAT_BAI_DIR / f"{_cache_key_bai(bai)}.json"


def build_prompt_tom_tat_bai(bai: dict) -> str:
    noi_dung = bai.get("content") or bai.get("summary", "")
    noi_dung = noi_dung[:TOM_TAT_BAI_MAX_KY_TU_NOI_DUNG]

    prompt = f"""Tóm tắt bài báo sau thành MỘT đoạn văn cô đọng (khoảng 4-8 câu), giữ lại đầy đủ
        các Ý CHÍNH, SỐ LIỆU, SỰ KIỆN, PHÁT BIỂU quan trọng nhất — đây sẽ là nguồn dữ liệu để
        viết bài tóm tắt cá nhân hóa sau này, nên KHÔNG được bỏ sót thông tin cốt lõi, nhưng
        cũng KHÔNG giữ nguyên văn các câu dài dòng, rườm rà, hoặc chi tiết phụ không cần thiết.

        Tiêu đề: {bai.get('title')}

        Nội dung gốc:
        {noi_dung}

        Chỉ trả về DUY NHẤT đoạn văn tóm tắt, không thêm tiêu đề, không thêm ghi chú, không
        dùng dấu ```.
        """.strip()

    return prompt


async def tom_tat_mot_bai(bai: dict, client, semaphore, model_name: str = OSS_MODEL_NAME) -> str:
    cache_path = _cache_path_bai(bai)
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)["tom_tat"]

    noi_dung_goc = bai.get("content") or bai.get("summary", "")
    if len(noi_dung_goc) <= TOM_TAT_BAI_MAX_TOKENS * 3:
        tom_tat = noi_dung_goc
        _ghi_cache_bai(cache_path, tom_tat)
        return tom_tat

    prompt = build_prompt_tom_tat_bai(bai)

    async def _call():
        return await client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.0,
                "max_output_tokens": TOM_TAT_BAI_MAX_TOKENS,
            },
        )

    print(f"[DEBUG] bắt đầu tóm tắt bài: {bai.get('link')}")
    async with semaphore:
        response = await retry_generate_async(_call)

    tom_tat = response.text.strip()
    if not tom_tat:
        tom_tat = noi_dung_goc[:TOM_TAT_BAI_MAX_KY_TU_NOI_DUNG]
    print(f"[DEBUG] xong tóm tắt bài: {bai.get('link')}")
    _ghi_cache_bai(cache_path, tom_tat)
    return tom_tat


def _ghi_cache_bai(cache_path: Path, tom_tat: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"tom_tat": tom_tat}, f, ensure_ascii=False, indent=2)


async def tom_tat_nhieu_bai(bai_list: list, client, semaphore, model_name: str = OSS_MODEL_NAME) -> dict:
    import asyncio

    ket_qua = {}

    async def _xu_ly(bai):
        tom_tat = await tom_tat_mot_bai(bai, client, semaphore, model_name)
        ket_qua[bai.get("link")] = tom_tat

    await asyncio.gather(*[_xu_ly(bai) for bai in bai_list])
    return ket_qua
