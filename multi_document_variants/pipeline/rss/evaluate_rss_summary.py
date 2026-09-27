"""
pipeline/rss/evaluate_rss_summary_gemini.py

Buoc 4 - Danh gia ban tom tat RSS ca nhan hoa bang LLM Judge (Gemini),
theo khung 6 tieu chi: chon_loc_phu_hop, nhat_quan, trinh_bay_phu_hop,
bo_cuc_uu_tien, giong_dieu_phu_hop, thai_do_dung_dan.

Doc file ket qua .json da sinh boi rss_personalize.py (khong doc .md,
vi .json co san ranked_articles/tin_gian_tiep de tra nguoc ve van ban nguon).
"""

import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from pipeline.utils import retry_generate, SUMMARY_MODEL_NAME

ROOT_DIR = Path(__file__).resolve().parents[3]
MD_ROOT = ROOT_DIR / "multi_document_variants"
SHARED_ROOT = ROOT_DIR / "shared"

DATA_DIR = MD_ROOT / "data"
OUTPUT_DIR = MD_ROOT / "output" / "rss_summary"
JSON_DIR = OUTPUT_DIR / "json"
EVAL_DIR = OUTPUT_DIR / "eval"

PERSONAS_PATH = DATA_DIR / "profile" / "state_profiles.json"
ARTICLES_PATH = DATA_DIR / "vnexpress_rss_snapshot.json"

TIEU_CHI = [
    "chon_loc_phu_hop",
    "nhat_quan",
    "trinh_bay_phu_hop",
    "bo_cuc_uu_tien",
    "giong_dieu_phu_hop",
    "thai_do_dung_dan",
]


def load_personas():
    with open(PERSONAS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_articles_index():
    with open(ARTICLES_PATH, encoding="utf-8") as f:
        articles = json.load(f)
    index_theo_link = {a.get("link"): a for a in articles if a.get("link")}
    index_theo_title = {a.get("title"): a for a in articles if a.get("title")}
    return index_theo_link, index_theo_title


def lay_noi_dung_nguon(ranked_items: list, index_theo_link: dict, index_theo_title: dict) -> tuple:
    """
    Voi moi item, thu tra theo link truoc, khong khop thi thu theo title.
    Uu tien lay noi dung day du (content), fallback ve summary (teaser ngan)
    neu bai khong co content. Tra ve (danh_sach_noi_dung, so_bai_khong_tim_thay).
    """
    ket_qua = []
    so_khong_tim_thay = 0
    for item in ranked_items:
        goc = index_theo_link.get(item.get("link")) or index_theo_title.get(item.get("title"))
        if goc:
            noi_dung = goc.get("content") or goc.get("summary", "")
            ket_qua.append({
                "title": goc.get("title", ""),
                "noi_dung": noi_dung,
                "genre": item.get("genre"),
            })
        else:
            so_khong_tim_thay += 1
            ket_qua.append({
                "title": item.get("title", ""),
                "noi_dung": "(không tìm thấy nội dung gốc - chỉ còn tiêu đề)",
                "genre": item.get("genre"),
            })
    return ket_qua, so_khong_tim_thay


def _format_nguon(nguon_list: list, nhan: str) -> str:
    if not nguon_list:
        return f"{nhan}: (không có)"
    dong = [f"{nhan}:"]
    for i, n in enumerate(nguon_list, 1):
        dong.append(f"{i}. [{n['genre']}] {n['title']}\n{n['noi_dung']}")
    return "\n".join(dong)


def build_judge_prompt(persona: dict, nguon_chinh: list, nguon_gian_tiep: list, summary: str) -> str:
    ho_so = f"""
Vai trò: {persona.get('kinh_nghiem', '')}
Đơn vị công tác: {persona.get('to_chuc', '')}
Ngành: {persona.get('nganh_to', '')} - {persona.get('nganh_nho', '')}
Chủ đề quan tâm (ưu tiên từ cao xuống thấp): {', '.join(persona.get('chu_de', []))}
Khuynh hướng/mối quan tâm trước mắt: {persona.get('cau_hoi_truoc_mat', '')}
Mô tả chung: {persona.get('mo_ta_chung', '')}
""".strip()

    nguon_text = (
        _format_nguon(nguon_chinh, "VĂN BẢN NGUỒN - nhóm tin chính (đúng chu_de persona)")
        + "\n\n"
        + _format_nguon(nguon_gian_tiep, "VĂN BẢN NGUỒN - nhóm tin liên quan gián tiếp")
    )

    prompt = f"""
Bạn là giám khảo đánh giá bản tóm tắt tin tức cá nhân hóa theo persona công chức/nhà nước.

HỒ SƠ PERSONA:
{ho_so}

{nguon_text}

BẢN TÓM TẮT CẦN CHẤM:
{summary}

Chấm bản tóm tắt trên theo đúng 6 tiêu chí sau, mỗi tiêu chí trả về "pass" hoặc "fail"
kèm lý do ngắn gọn (tối đa 2 câu, tiếng Việt có dấu):

1. chon_loc_phu_hop: Bản tóm tắt có ưu tiên chọn chi tiết/dữ kiện liên quan trực tiếp
   đến chu_de và khuynh hướng quan tâm của persona không, có bỏ sót chi tiết quan trọng
   đúng chuyên môn không, có giữ nhiều chi tiết không liên quan không.
2. nhat_quan: Mọi thông tin trong bản tóm tắt có đúng với văn bản nguồn không (không bịa
   thêm số liệu/sự kiện), các câu trong bản tóm tắt có mâu thuẫn nhau không, có gán cho
   persona đặc điểm/quan điểm không có trong hồ sơ không.
3. trinh_bay_phu_hop: Độ dài có vượt quá văn bản nguồn không; nếu tin đúng chuyên môn
   persona thì có dùng thuật ngữ/bố cục kiểu chuyên gia không, nếu tin KHÔNG đúng chuyên
   môn persona thì có trình bày ở mức phổ thông, không lạm dụng thuật ngữ chuyên ngành
   không cần thiết không; câu văn có rõ ràng mạch lạc, không lặp ý không.
4. bo_cuc_uu_tien: Nội dung liên quan nhất với persona có được đặt lên đầu/nổi bật không,
   nội dung phụ có được đẩy xuống sau hoặc lược bớt không.
5. giong_dieu_phu_hop: Giọng điệu có phù hợp với vị trí công tác và mục đích sử dụng
   (tham mưu/theo dõi chuyên ngành) của persona không, có quá suồng sã hoặc quá hoa mỹ
   không cần thiết không; bản tóm tắt có GIỮ ĐÚNG tính chất định hướng/khuynh hướng của
   mối quan tâm persona mà KHÔNG biến thành câu hỏi trực tiếp hay lời khuyên/kêu gọi
   hành động lộ liễu không.
6. thai_do_dung_dan: Bản tóm tắt có giữ thái độ khách quan trung lập không, có câu phán
   xét/thiên vị/suy diễn động cơ không, có tôn trọng đúng mực vai trò persona không.

Với MỖI tiêu chí (cả pass lẫn fail), ly_do PHẢI nêu ít nhất 1 ví dụ cụ thể: một chi
tiết/câu trong bản tóm tắt, đối chiếu với một chi tiết tương ứng trong hồ sơ persona
hoặc văn bản nguồn. Không được viết lý do chung chung không có dẫn chứng cụ thể.

CHỈ trả về một đối tượng JSON đúng định dạng sau, không thêm lời dẫn, không dùng markdown:
{{
  "chon_loc_phu_hop": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "nhat_quan": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "trinh_bay_phu_hop": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "bo_cuc_uu_tien": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "giong_dieu_phu_hop": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "thai_do_dung_dan": {{"verdict": "pass hoặc fail", "ly_do": "..."}}
}}
""".strip()

    return prompt


def cham_1_persona(persona: dict, ket_qua_rss: dict, index_theo_link: dict, index_theo_title: dict, client,
                    model_name: str = SUMMARY_MODEL_NAME) -> dict:
    summary = ket_qua_rss.get("summary", "")
    if not summary:
        return {
            "id": persona.get("id"),
            "note": "Bỏ qua đánh giá - bản tóm tắt rỗng (không có tin khớp chu_de).",
        }

    nguon_chinh, thieu_1 = lay_noi_dung_nguon(ket_qua_rss.get("ranked_articles", []), index_theo_link, index_theo_title)
    nguon_gian_tiep, thieu_2 = lay_noi_dung_nguon(ket_qua_rss.get("tin_gian_tiep", []), index_theo_link, index_theo_title)
    tong_bai = len(ket_qua_rss.get("ranked_articles", [])) + len(ket_qua_rss.get("tin_gian_tiep", []))
    tong_thieu = thieu_1 + thieu_2

    prompt = build_judge_prompt(persona, nguon_chinh, nguon_gian_tiep, summary)

    def _call():
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )

    response = retry_generate(_call)

    raw = response.text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        cham = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "id": persona.get("id"),
            "note": "LỖI: không parse được JSON từ Gemini, xem raw_response.",
            "raw_response": raw,
        }

    so_dat = sum(1 for tc in TIEU_CHI if cham.get(tc, {}).get("verdict") == "pass")

    ket_qua_cham = {
        "id": persona.get("id"),
        "tieu_chi": cham,
        "so_tieu_chi_dat": so_dat,
        "verdict_cuoi": "DAT" if so_dat == len(TIEU_CHI) else "KHONG_DAT",
    }
    if tong_thieu > 0:
        ket_qua_cham["canh_bao_thieu_nguon"] = (
            f"{tong_thieu}/{tong_bai} bài không khớp được với văn bản nguồn "
            f"(chỉ còn tiêu đề) - kết quả chấm có thể KHÔNG ĐÁNG TIN CẬY."
        )

    return ket_qua_cham


if __name__ == "__main__":
    import argparse
    from google import genai

    API_KEY = os.getenv("API_KEY")

    parser = argparse.ArgumentParser(description="Đánh giá bản tóm tắt RSS bằng LLM Judge (Gemini)")
    parser.add_argument("--id", type=str, help="id của persona, ví dụ NN0001")
    parser.add_argument("-n", "--so-luong", type=int, help="Chỉ đánh giá N kết quả đầu tiên")
    args = parser.parse_args()

    personas = load_personas()
    persona_index = {p["id"]: p for p in personas}
    index_theo_link, index_theo_title = load_articles_index()
    client = genai.Client(api_key=API_KEY)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    if args.id:
        json_path = JSON_DIR / f"{args.id}.json"
        if not json_path.exists():
            raise SystemExit(f"Không tìm thấy kết quả rss_personalize cho id = {args.id}")
        with open(json_path, encoding="utf-8") as f:
            ket_qua_rss = json.load(f)
        persona = persona_index.get(args.id)
        if persona is None:
            raise SystemExit(f"Không tìm thấy persona có id = {args.id}")

        print(f"[{args.id}] đang chấm...")
        cham = cham_1_persona(persona, ket_qua_rss, index_theo_link, index_theo_title, client)
        out_path = EVAL_DIR / f"{args.id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cham, f, ensure_ascii=False, indent=2)
        print(f"[{args.id}] xong -> {out_path}")
    else:
        danh_sach_file = sorted(JSON_DIR.glob("*.json"))
        if args.so_luong:
            danh_sach_file = danh_sach_file[:args.so_luong]

        print("Tổng số kết quả cần chấm:", len(danh_sach_file))
        t_bat_dau = time.time()
        thong_ke_dat = 0
        thong_ke_khong_dat = 0
        thong_ke_bo_qua = 0

        for json_path in danh_sach_file:
            persona_id = json_path.stem
            out_path = EVAL_DIR / f"{persona_id}.json"
            if out_path.exists():
                print(f"[{persona_id}] đã chấm rồi, bỏ qua.")
                continue

            persona = persona_index.get(persona_id)
            if persona is None:
                print(f"[{persona_id}] không tìm thấy persona tương ứng, bỏ qua.")
                continue

            with open(json_path, encoding="utf-8") as f:
                ket_qua_rss = json.load(f)

            print(f"[{persona_id}] đang chấm...")
            cham = cham_1_persona(persona, ket_qua_rss, index_theo_link, index_theo_title, client)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(cham, f, ensure_ascii=False, indent=2)

            if cham.get("verdict_cuoi") == "DAT":
                thong_ke_dat += 1
            elif cham.get("verdict_cuoi") == "KHONG_DAT":
                thong_ke_khong_dat += 1
            else:
                thong_ke_bo_qua += 1

        print("\nXONG HẾT. Tổng thời gian:", round((time.time() - t_bat_dau) / 60, 1), "phút")
        print(f"ĐẠT cả 6 tiêu chí: {thong_ke_dat}")
        print(f"KHÔNG ĐẠT (thiếu ít nhất 1 tiêu chí): {thong_ke_khong_dat}")
        print(f"Bỏ qua (rỗng/lỗi/không có persona): {thong_ke_bo_qua}")