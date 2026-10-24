import json
import time
import re
import hashlib
import asyncio
from pathlib import Path
from pipeline.utils import (
    retry_generate_async, OSS_MODEL_NAME, tao_oss_client_async,
    OSS_MAX_CONCURRENCY_SUMMARY,
)
from pipeline.baochi.bao_chi_personalize_gpt import BANNED_PHRASES, load_articles, _dam_bao_co_link
ROOT_DIR = Path(__file__).resolve().parents[3]
MD_ROOT = ROOT_DIR / "multi_document_variants"
SHARED_ROOT = ROOT_DIR / "shared"

DATA_DIR = MD_ROOT / "data" / "bao_chi"
OUTPUT_DIR = MD_ROOT / "output" / "bao_chi" / "rss_summary"
TOM_TAT_BAI_DIR = MD_ROOT / "output" / "bao_chi" / "rss_tom_tat_bai"

TIEU_CHI_CAN_NGUON = ["chon_loc_phu_hop", "nhat_quan"]
TIEU_CHI_HINH_THUC = ["trinh_bay_phu_hop", "bo_cuc_uu_tien", "giong_dieu_phu_hop", "thai_do_dung_dan"]
TIEU_CHI = TIEU_CHI_CAN_NGUON + TIEU_CHI_HINH_THUC  # giữ đúng thứ tự cũ để dễ so sánh kết quả

NGUON_JUDGE_MAX_TOKENS = 2048
NGUON_JUDGE_MAX_TOKENS_MO_RONG = 4096
HINH_THUC_JUDGE_MAX_TOKENS = 3072
HINH_THUC_JUDGE_MAX_TOKENS_MO_RONG = 6144
NGUONG_TI_LE_PASS_BATCH = 0.8

def load_personas(variant=None):
    ten_file = f"state_profiles_{variant}.json" if variant else "state_profiles_nt_nn_tc_kn_cd_ch.json"
    duong_dan = MD_ROOT / "data" / "profile" / ten_file
    with open(duong_dan, encoding="utf-8") as f:
        return json.load(f)


def load_articles_index(duong_dan_data: Path):
    articles = load_articles(duong_dan_data)
    articles = _dam_bao_co_link(articles)  # phải khớp đúng cách sinh link giả mà rss_personalize.py đã dùng
    index_theo_link = {a.get("link"): a for a in articles if a.get("link")}
    index_theo_title = {a.get("title"): a for a in articles if a.get("title")}
    return index_theo_link, index_theo_title


def _doc_tom_tat_bai(link: str) -> str:
    """Đọc lại bản tóm tắt tầng 1 (đã cache sẵn khi rss_personalize.py chạy, cache theo link,
    hoàn toàn miễn phí - không tốn thêm lượt gọi LLM nào). Đây CHÍNH XÁC là nội dung nguồn mà
    LLM viết bài đã nhìn thấy (không phải văn bản gốc đầy đủ) - nên evaluate cũng dùng lại đúng
    bản này để chấm cho công bằng, thay vì đối chiếu với nội dung LLM chưa từng thấy."""
    if not link:
        return "(không có link)"
    key = hashlib.md5(link.encode("utf-8")).hexdigest()[:16]
    duong_dan = TOM_TAT_BAI_DIR / f"{key}.json"
    if not duong_dan.exists():
        return "(không tìm thấy bản tóm tắt tầng 1 trong cache - có thể cache đã bị xoá)"
    with open(duong_dan, encoding="utf-8") as f:
        return json.load(f).get("tom_tat", "")


def lay_noi_dung_nguon_C(tin_links: list) -> list:
    """Nguồn cho nhóm tin CHÍNH (C) - dùng bản tầng 1 cô đọng (đúng cái LLM viết bài đã thấy)."""
    ket_qua = []
    for link in tin_links:
        ket_qua.append({"link": link, "noi_dung": _doc_tom_tat_bai(link)})
    return ket_qua


def lay_noi_dung_nguon_GB(items: list, index_theo_link: dict, index_theo_title: dict) -> tuple:
    """Nguồn cho nhóm tin gián tiếp (G) / bài góc nhìn (B) - dùng field "summary" (RSS gốc), vì
    đây đúng là nội dung LLM viết bài đã thấy cho 2 nhóm này (dung_full_content=False khi build
    prompt ở rss_personalize.py), KHÔNG dùng content đầy đủ."""
    ket_qua = []
    so_khong_tim_thay = 0
    for item in items:
        goc = index_theo_link.get(item.get("link")) or index_theo_title.get(item.get("title"))
        if goc:
            ket_qua.append({
                "title": goc.get("title", ""),
                "noi_dung": goc.get("summary", ""),
                "genre": item.get("genre", "Góc nhìn"),
            })
        else:
            so_khong_tim_thay += 1
            ket_qua.append({
                "title": item.get("title", ""),
                "noi_dung": "(không tìm thấy nội dung gốc - chỉ còn tiêu đề)",
                "genre": item.get("genre", "Góc nhìn"),
            })
    return ket_qua, so_khong_tim_thay


def _format_nguon(nguon_list: list, nhan: str, prefix: str) -> str:
    if not nguon_list:
        return f"{nhan}: (không có)"
    dong = [f"{nhan}:"]
    for i, n in enumerate(nguon_list, 1):
        tieu_de = n.get("title", "")
        the_loai = f"[{n['genre']}] " if n.get("genre") else ""
        dong.append(f"{prefix}{i}. {the_loai}{tieu_de}\n{n['noi_dung']}")
    return "\n".join(dong)


def _chuan_hoa(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()

def _chuan_hoa_ten_nhom(s: str) -> str:
    s = re.sub(r"[/\-,&]", " ", s or "")
    return _chuan_hoa(s)

def _trich_cac_doan_trich_dan(text: str) -> list:
    """Tìm tất cả cụm được đặt trong dấu ngoặc kép (kiểu " " hoặc " ") trong ly_do."""
    ket_qua = []
    ket_qua.extend(re.findall(r'"([^"]{5,})"', text))
    ket_qua.extend(re.findall(r'\u201c([^\u201d]{5,})\u201d', text))
    return ket_qua


def hau_kiem_fail_reasons_batch(nhan_batch: str, cham: dict, batch_text: str,
                                 nguon_c: list, nguon_g: list, nguon_b: list) -> dict:
    canh_bao = []
    tc_bi_bia = set()  # tiêu chí mà TOÀN BỘ bằng chứng trích dẫn của fail đều bịa/suy diễn
    batch_text_chuan = _chuan_hoa(batch_text)
    nguon_text_chuan = _chuan_hoa(
        " ".join(n.get("noi_dung", "") for n in nguon_c)
        + " " + " ".join((n.get("noi_dung", "") + " " + n.get("title", "")) for n in nguon_g + nguon_b)
    )
    van_ban_chuan_gop = batch_text_chuan + " " + nguon_text_chuan
    so_c, so_g, so_b = len(nguon_c), len(nguon_g), len(nguon_b)

    for tc, ket in cham.items():
        if not isinstance(ket, dict) or ket.get("verdict") != "fail":
            continue
        ly_do = ket.get("ly_do", "")
        cac_trich_dan = _trich_cac_doan_trich_dan(ly_do)
        so_trich_bia = 0

        for tien_to, so_str in re.findall(r"\b([CGB])(\d+)\b", ly_do):
            so = int(so_str)
            if tien_to == "C" and so > so_c:
                canh_bao.append(f"[{nhan_batch}/{tc}] trích mã C{so} không tồn tại (batch này chỉ có {so_c} tin).")
            if tien_to == "G" and so > so_g:
                canh_bao.append(f"[{nhan_batch}/{tc}] trích mã G{so} không tồn tại (nhóm gián tiếp chỉ có {so_g} tin).")
            if tien_to == "B" and so > so_b:
                canh_bao.append(f"[{nhan_batch}/{tc}] trích mã B{so} không tồn tại (nhóm góc nhìn chỉ có {so_b} bài).")

        for trich in cac_trich_dan:
            if _chuan_hoa(trich) not in van_ban_chuan_gop:
                so_trich_bia += 1
                canh_bao.append(
                    f"[{nhan_batch}/{tc}] trích dẫn \"{trich[:60]}...\" KHÔNG có trong CẢ đoạn "
                    f"thân bài lẫn văn bản nguồn của batch này - có khả năng judge bịa nội dung."
                )

        co_claim_bo_sot = any(tu in ly_do.lower() for tu in ["bỏ sót", "bỏ qua", "thiếu nội dung", "không đề cập"])
        if co_claim_bo_sot:
            if not cac_trich_dan:
                canh_bao.append(
                    f"[{nhan_batch}/{tc}] verdict fail với lý do bỏ sót/thiếu nhưng KHÔNG trích dẫn bằng "
                    f"chứng cụ thể nào - có khả năng judge hallucinate, cần soát tay."
                )
            for trich in cac_trich_dan:
                trich_chuan = _chuan_hoa(trich)
                if trich_chuan and trich_chuan not in nguon_text_chuan:
                    so_trich_bia += 1
                    canh_bao.append(
                        f"[{nhan_batch}/{tc}] cho rằng bản tóm tắt bỏ sót \"{trich[:60]}...\" nhưng nội dung "
                        f"này KHÔNG tìm thấy trong văn bản nguồn của batch - có khả năng judge suy diễn."
                    )

        if cac_trich_dan and so_trich_bia >= len(cac_trich_dan):
            tc_bi_bia.add(tc)

    return {"can_soat_tay": bool(canh_bao), "chi_tiet_canh_bao": canh_bao, "tc_bi_bia": tc_bi_bia}

def hau_kiem_hallucination_hinh_thuc(cham: dict, summary: str) -> tuple:
    canh_bao = []
    summary_chuan = _chuan_hoa(summary)
    for tc in ("trinh_bay_phu_hop", "giong_dieu_phu_hop", "thai_do_dung_dan"):
        ket = cham.get(tc)
        if not isinstance(ket, dict) or ket.get("verdict") != "fail":
            continue
        ly_do = ket.get("ly_do", "")
        cac_trich_dan = _trich_cac_doan_trich_dan(ly_do)
        if not cac_trich_dan:
            canh_bao.append(f"[{tc}] verdict fail nhưng KHÔNG trích dẫn bằng chứng cụ thể - cần soát tay.")
            continue
        so_bia = sum(1 for t in cac_trich_dan if _chuan_hoa(t) not in summary_chuan)
        if so_bia == len(cac_trich_dan):
            ly_do_goc = ly_do
            cham[tc] = {
                "verdict": "pass",
                "ly_do": (
                    f"[HẬU KIỂM TỰ ĐỘNG - LẬT VERDICT] Toàn bộ trích dẫn judge đưa ra làm bằng "
                    f"chứng fail đều KHÔNG có thật trong bản tóm tắt (khả năng judge bịa) -> tự "
                    f"động chuyển pass. Lý do judge gốc (không dùng để quyết định): {ly_do_goc}"
                ),
            }
            canh_bao.append(f"[{tc}] đã tự động lật fail->pass do toàn bộ trích dẫn bịa.")
        elif so_bia > 0:
            canh_bao.append(
                f"[{tc}] fail với {so_bia}/{len(cac_trich_dan)} trích dẫn không khớp thực tế trong "
                f"bản tóm tắt - giữ nguyên verdict nhưng cần soát tay."
            )
    return cham, canh_bao

_TU_KHOA_YEU_CAU_CHUYEN_SAU = ("thuật ngữ", "chuyên sâu", "chuyên môn", "chuyên ngành", "phổ thông", "cấu trúc cố định")


def hau_kiem_mien_chuyen_sau(cham: dict, summary: str, than_bai_text: str, cac_batch: list) -> tuple:
    canh_bao = []
    if not cac_batch:
        return cham, canh_bao
    nhom_uu_tien_1 = cac_batch[0].get("nhom_chu_de", "")
    text_nhom_1_chuan = _chuan_hoa(
        "\n\n".join(b.get("text", "") for b in cac_batch if b.get("nhom_chu_de", "") == nhom_uu_tien_1)
    )
    than_bai_chuan = _chuan_hoa(than_bai_text)
    summary_chuan = _chuan_hoa(summary)

    for tc in ("trinh_bay_phu_hop", "giong_dieu_phu_hop"):
        ket = cham.get(tc)
        if not isinstance(ket, dict) or ket.get("verdict") != "fail":
            continue
        ly_do = ket.get("ly_do", "")
        if not any(tu in ly_do.lower() for tu in _TU_KHOA_YEU_CAU_CHUYEN_SAU):
            continue
        cac_trich_dan = _trich_cac_doan_trich_dan(ly_do)
        if not cac_trich_dan:
            continue

        def _duoc_mien(t):
            tc_chuan = _chuan_hoa(t)
            if not tc_chuan or tc_chuan not in summary_chuan:
                return False  # không xác minh được vị trí thật -> không tự lật, giữ nguyên
            if tc_chuan not in than_bai_chuan:
                return True  # ngoài thân bài -> mở bài/kết luận/tin liên quan/góc nhìn -> miễn
            return tc_chuan not in text_nhom_1_chuan  # trong thân bài nhưng khác nhóm ưu tiên #1 -> miễn

        if all(_duoc_mien(t) for t in cac_trich_dan):
            ly_do_goc = ly_do
            cham[tc] = {
                "verdict": "pass",
                "ly_do": (
                    f"[HẬU KIỂM TỰ ĐỘNG - LẬT VERDICT] Bằng chứng judge trích dẫn đều nằm ở phần "
                    f"KHÔNG bắt buộc chuyên sâu (mở bài/kết luận/tin liên quan/góc nhìn, hoặc thân "
                    f"bài của nhóm không phải ưu tiên cao nhất) -> tự động chuyển pass. Lý do judge "
                    f"gốc (không dùng để quyết định): {ly_do_goc}"
                ),
            }
            canh_bao.append(f"[{tc}] đã tự động lật fail->pass do bằng chứng nằm ngoài vùng bắt buộc chuyên sâu.")

    return cham, canh_bao

def hau_kiem_cum_tu_cam(than_bai_text: str) -> list:
    vi_pham = []
    for doan in (d.strip() for d in than_bai_text.split("\n\n") if d.strip()):
        for cau in re.split(r"(?<=[.!?])\s+", doan):
            cau_norm = cau.strip()
            cau_norm_lower = cau_norm.lower()
            for p in BANNED_PHRASES:
                if cau_norm_lower.startswith(p.lower()):
                    vi_pham.append(f"{p!r} mở đầu câu: \"{cau_norm[:70]}\"")
                    break
    return vi_pham

def hau_kiem_bo_cuc_uu_tien(cac_batch: list) -> list:
    vi_pham = []
    for i in range(1, len(cac_batch)):
        nhom_truoc = cac_batch[i - 1].get("nhom_chu_de", "")
        nhom_hien_tai = cac_batch[i].get("nhom_chu_de", "")
        if nhom_hien_tai == nhom_truoc:
            continue
        text_dau_doan = cac_batch[i].get("text", "")[:200]
        if _chuan_hoa_ten_nhom(nhom_hien_tai) not in _chuan_hoa_ten_nhom(text_dau_doan):
            vi_pham.append(
                f"Chuyển sang nhóm \"{nhom_hien_tai}\" nhưng KHÔNG thấy tên nhóm trong 200 ký tự "
                f"đầu đoạn: \"{text_dau_doan[:80]}...\""
            )
    return vi_pham

def build_judge_prompt_nguon(persona: dict, nguon_c: list, nguon_g: list, nguon_b: list,
                              batch_text: str, nhom_ten: str) -> str:
    ho_so = f"""
Vai trò: {persona.get('kinh_nghiem', '')}
Đơn vị công tác: {persona.get('to_chuc', '')}
Ngành: {persona.get('nganh_to', '')} - {persona.get('nganh_nho', '')}
Chủ đề quan tâm (ưu tiên từ cao xuống thấp): {', '.join(persona.get('chu_de', []))}
Khuynh hướng/mối quan tâm trước mắt: {persona.get('cau_hoi_truoc_mat', '')}
Mô tả chung: {persona.get('mo_ta_chung', '')}
""".strip()

    nguon_text = (
        _format_nguon(nguon_c, f"VĂN BẢN NGUỒN - nhóm tin chính thuộc chủ đề \"{nhom_ten}\" (phần đang chấm)", "C")
        + "\n\n"
        + _format_nguon(nguon_g, "VĂN BẢN NGUỒN - nhóm tin liên quan gián tiếp (toàn bộ persona)", "G")
        + "\n\n"
        + _format_nguon(nguon_b, "VĂN BẢN NGUỒN - nhóm bài góc nhìn/phân tích liên quan (toàn bộ persona)", "B")
    )

    prompt = f"""
Bạn là giám khảo đánh giá MỘT PHẦN của bản tóm tắt tin tức cá nhân hóa theo persona công chức/nhà
nước. Đây KHÔNG phải toàn bộ bản tóm tắt — chỉ là phần thân bài ứng với nhóm chủ đề "{nhom_ten}",
được viết riêng cho đúng {len(nguon_c)} tin nguồn dưới đây. Nhóm tin gián tiếp (G) và bài góc nhìn
(B) là của TOÀN BỘ persona (dùng chung cho mọi phần), chỉ đưa vào đây để bạn có đủ ngữ cảnh kiểm
tra, KHÔNG bắt buộc phải xuất hiện trong đoạn văn đang chấm.

HỒ SƠ PERSONA:
{ho_so}

{nguon_text}

LƯU Ý VỀ ĐÁNH SỐ: mã C1, C2... trong lượt chấm này CHỈ đánh số cục bộ cho {len(nguon_c)} tin
thuộc phần đang chấm — KHÔNG liên quan tới số thứ tự tin ở các phần khác của cùng persona (được
chấm ở lượt riêng). Mã G/B đánh số cho toàn bộ persona như bình thường.

ĐOẠN THÂN BÀI CẦN CHẤM (đúng phần ứng với {len(nguon_c)} tin nguồn C ở trên):
{batch_text}

BƯỚC BẮT BUỘC TRƯỚC KHI CHẤM (chỉ để bạn tự suy luận, KHÔNG in ra kết quả): với MỖI tin C1,
C2... ở trên, xác định nó được phản ánh ở đâu trong đoạn thân bài. Nếu 2 tin C.. cùng nằm chung
1 đoạn văn (không tách dòng trống), đó là gộp — chỉ hợp lệ nếu 2 tin đó THẬT SỰ cùng nói về MỘT
SỰ KIỆN CỤ THỂ (trùng tên riêng/đơn vị/địa điểm, trùng mốc thời gian, trùng hành động/quyết
định); nếu là hai sự kiện khác nhau bị gộp chung, hoặc một tin bị bỏ hẳn không xuất hiện, đó là
lỗi thật — kết luận fail cho chon_loc_phu_hop, trích rõ mã C liên quan.

Chấm phần thân bài này theo đúng 2 tiêu chí sau, mỗi tiêu chí trả về "pass" hoặc "fail" kèm lý do
ngắn gọn (tối đa 2 câu, tiếng Việt có dấu):

1. chon_loc_phu_hop: Đoạn thân bài này có ưu tiên chọn chi tiết/dữ kiện liên quan trực tiếp đến
   chu_de và khuynh hướng quan tâm của persona không, có bỏ sót chi tiết quan trọng đúng chuyên
   môn không, có giữ nhiều chi tiết không liên quan không. Với các đoạn gộp 2 tin C.. cùng sự
   kiện: áp dụng đúng quy tắc xác nhận trùng sự kiện ở trên, không tự động coi gộp là lỗi.
   LƯU Ý VỀ "KHUYNH HƯỚNG QUAN TÂM TRƯỚC MẮT": yêu cầu nội dung phải phản ánh/dẫn dắt theo khuynh
   hướng quan tâm trước mắt của persona CHỈ áp dụng cho nhóm chủ đề ƯU TIÊN CAO NHẤT (nhóm số 1
   trong "Chủ đề quan tâm" ở hồ sơ). Nếu nhóm "{nhom_ten}" đang chấm KHÔNG phải nhóm ưu tiên cao
   nhất, KHÔNG được fail chon_loc_phu_hop chỉ vì nội dung không nhắc tới khuynh hướng quan tâm
   trước mắt - nhóm ưu tiên thấp hơn chỉ cần đúng chuyên môn/chủ đề của chính nhóm đó là đủ.
2. nhat_quan: Mọi thông tin trong đoạn thân bài này có đúng với văn bản nguồn C.. không (không
   bịa thêm số liệu/sự kiện), các câu có mâu thuẫn nhau không, có gán cho persona đặc điểm/quan
   điểm không có trong hồ sơ không.

Với MỖI tiêu chí (cả pass lẫn fail), ly_do PHẢI nêu ít nhất 1 ví dụ cụ thể, dùng mã C../G../B..
khi trích dẫn tin nguồn. QUY TẮC TRÍCH DẪN BẮT BUỘC: mọi ly_do khẳng định "fail" PHẢI trích một
cụm từ/câu NGẮN thực sự có trong đoạn thân bài ở trên làm bằng chứng, đặt trong dấu ngoặc kép.
Nếu không thể trích dẫn cụ thể như vậy, KHÔNG được kết luận "fail" - chuyển sang "pass".

QUY TẮC CHỐNG SUY DIỄN NGUỒN KHÔNG TỒN TẠI: nếu ly_do phê bình "bỏ sót" một nội dung nào đó, BẮT
BUỘC phải chỉ ra đúng mã C../G../B.. trong danh sách nguồn ở trên có chứa đúng nội dung đó. Nếu
rà soát toàn bộ mà không tìm thấy, đây là suy diễn sai - TUYỆT ĐỐI không dùng làm lý do fail.

QUY TẮC MẶC ĐỊNH KHI CHẤM: đánh giá công bằng, không cần khắt khe với các khác biệt rất nhỏ hoặc
không ảnh hưởng đáng kể tới độ chính xác/mức độ phù hợp của nội dung. Chỉ kết luận "fail" khi có
bằng chứng RÕ RÀNG, CỤ THỂ về vi phạm (đúng như quy tắc trích dẫn bắt buộc ở trên); nếu chỉ là
cảm nhận chủ quan hoặc sự khác biệt không đáng kể, chọn "pass".

CHỈ trả về một đối tượng JSON đúng định dạng sau, không thêm lời dẫn, không dùng markdown, CHỈ 2
khóa, mỗi khóa là MỘT OBJECT có ĐÚNG 2 trường "verdict" và "ly_do":
{{
  "chon_loc_phu_hop": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "nhat_quan": {{"verdict": "pass hoặc fail", "ly_do": "..."}}
}}
""".strip()

    return prompt


def build_judge_prompt_hinh_thuc(persona: dict, summary: str, ten_cac_nhom: list, day_du: bool) -> str:
    ho_so = f"""
Vai trò: {persona.get('kinh_nghiem', '')}
Đơn vị công tác: {persona.get('to_chuc', '')}
Ngành: {persona.get('nganh_to', '')} - {persona.get('nganh_nho', '')}
Chủ đề quan tâm (ưu tiên từ cao xuống thấp): {', '.join(persona.get('chu_de', []))}
Khuynh hướng/mối quan tâm trước mắt: {persona.get('cau_hoi_truoc_mat', '')}
Mô tả chung: {persona.get('mo_ta_chung', '')}
""".strip()

    thu_tu_nhom = " -> ".join(ten_cac_nhom) if ten_cac_nhom else "(không có nhóm nào)"

    cau_truc_ghi_chu = f"""
CẤU TRÚC CỐ ĐỊNH của bản tóm tắt (để bạn xác định đúng vai trò từng đoạn trước khi chấm, KHÔNG
in ra): {"1) tiêu đề  2) mở bài  " if day_du else "(không có tiêu đề/mở bài riêng - đoạn đầu tiên có dòng dẫn ngắn kiểu 'Về [chủ đề]:')  "}
3) thân bài theo các nhóm chủ đề theo đúng thứ tự ưu tiên: {thu_tu_nhom}  4) đoạn kết luận -
chốt lại các ý chính của TIN CHÍNH (thân bài ở mục 3), đứng NGAY SAU thân bài, KHÔNG phải đoạn
cuối cùng của toàn văn bản  5) đoạn tin gián tiếp (nếu có, thường mở đầu "Các tin khác đáng chú
ý:")  6) đoạn bài góc nhìn liên quan (nếu có, đoạn đầu mở đầu "Góc nhìn liên quan:") - đây mới
là ĐOẠN CUỐI CÙNG THẬT SỰ của toàn bộ bản tóm tắt (nếu nhóm 5/6 tồn tại). TUYỆT ĐỐI không nhầm
đoạn kết luận ở mục 4 với đoạn cuối của nhóm tin gián tiếp/góc nhìn ở mục 5/6 - đối chiếu nội
dung: kết luận tổng kết TIN CHÍNH, đoạn tin gián tiếp/góc nhìn chỉ tóm tắt các tin/bài PHỤ nằm
ngoài chủ đề chính. Việc đoạn tin gián tiếp/góc nhìn xuất hiện SAU đoạn kết luận là ĐÚNG THIẾT
KẾ, KHÔNG được coi là lỗi bố cục.

LƯU Ý VỀ MỨC ĐỘ THUẬT NGỮ: thân bài ở mục 3 được viết với ĐỘ SÂU GIẢM DẦN theo đúng thứ tự ưu
tiên nhóm chủ đề ở trên - nhóm ưu tiên cao nhất dùng thuật ngữ chuyên ngành sâu, nhóm ưu tiên
thấp hơn (đặc biệt từ nhóm ưu tiên thứ 3 trở đi) CHỦ ĐÍCH dùng ngôn ngữ phổ thông, hạn chế thuật
ngữ chuyên ngành. Đây là THIẾT KẾ CÓ CHỦ Ý để làm nổi bật nội dung quan trọng nhất, KHÔNG được
coi là lỗi thiếu nhất quán về giọng điệu/thuật ngữ khi chấm trinh_bay_phu_hop và
giong_dieu_phu_hop - chỉ fail nếu MỘT đoạn cụ thể tự nó dùng từ ngữ suồng sã/không phù hợp với
persona, chứ không phải vì có sự chênh lệch mức độ chuyên sâu GIỮA các đoạn khác nhau.

LƯU Ý QUAN TRỌNG VỀ MỞ BÀI/KẾT LUẬN/TIN LIÊN QUAN: yêu cầu "thuật ngữ/bố cục kiểu chuyên gia" ở
trinh_bay_phu_hop CHỈ áp dụng cho phần THÂN BÀI (mục 3) của nhóm ưu tiên cao nhất. Đoạn MỞ BÀI
(mục 2, nếu có) và đoạn KẾT LUẬN (mục 4) LUÔN được viết ở mức khái quát, ngắn gọn, KHÔNG đi vào
thuật ngữ chuyên sâu theo đúng yêu cầu thiết kế - TUYỆT ĐỐI KHÔNG trích dẫn nội dung mở bài hoặc
kết luận làm bằng chứng fail cho trinh_bay_phu_hop/giong_dieu_phu_hop vì lý do "thiếu thuật ngữ
chuyên sâu"/"ngôn ngữ phổ thông". Tương tự, đoạn tin gián tiếp (mục 5) và bài góc nhìn (mục 6) là
nội dung PHỤ, luôn viết súc tích/phổ thông theo thiết kế, cũng KHÔNG bị đòi hỏi thuật ngữ chuyên
sâu.

BƯỚC BẮT BUỘC TRƯỚC KHI KẾT LUẬN FAIL cho trinh_bay_phu_hop hoặc giong_dieu_phu_hop (chỉ để bạn tự
suy luận, KHÔNG in ra): xác định đoạn trích dẫn định dùng làm bằng chứng thuộc phần nào trong 6
phần ở CẤU TRÚC CỐ ĐỊNH trên. Nếu đoạn đó thuộc mở bài/kết luận/tin gián tiếp/bài góc nhìn (mục
2/4/5/6), KHÔNG được dùng làm bằng chứng cho lỗi "thiếu chuyên sâu" - chỉ được dùng nếu đoạn đó
thuộc THÂN BÀI của nhóm ưu tiên cao nhất (mục 3, nhóm đầu tiên trong: {thu_tu_nhom}).
""".strip()

    prompt = f"""
Bạn là giám khảo đánh giá HÌNH THỨC TRÌNH BÀY của một bản tóm tắt tin tức cá nhân hóa theo persona
công chức/nhà nước (KHÔNG cần đối chiếu với văn bản nguồn gốc từng tin ở bước này - việc đó đã
được chấm riêng ở bước khác).

HỒ SƠ PERSONA:
{ho_so}

{cau_truc_ghi_chu}

BẢN TÓM TẮT CẦN CHẤM (toàn văn):
{summary}

Chấm bản tóm tắt trên theo đúng 3 tiêu chí sau, mỗi tiêu chí trả về "pass" hoặc "fail" kèm lý do
ngắn gọn (tối đa 2 câu, tiếng Việt có dấu), PHẢI trích 1 cụm/câu NGẮN thực sự có trong bản tóm
tắt làm bằng chứng khi kết luận "fail":

1. trinh_bay_phu_hop: Nếu persona có chuyên môn đúng chủ đề nhóm ưu tiên cao nhất thì có dùng
   thuật ngữ/bố cục kiểu chuyên gia không, nếu không đúng chuyên môn thì có trình bày ở mức phổ
   thông, không lạm dụng thuật ngữ chuyên ngành không cần thiết không; câu văn có rõ ràng mạch
   lạc, không lặp ý không.
2. giong_dieu_phu_hop: Giọng điệu có phù hợp với vị trí công tác và mục đích tham mưu/theo dõi
   chuyên ngành của persona không, có quá suồng sã hoặc quá hoa mỹ không cần thiết không; bản tóm
   tắt có GIỮ ĐÚNG tính chất định hướng/khuynh hướng mối quan tâm của persona mà KHÔNG biến thành
   câu hỏi trực tiếp hay lời khuyên/kêu gọi hành động lộ liễu không.
3. thai_do_dung_dan: Bản tóm tắt có giữ thái độ khách quan trung lập không, có câu phán xét/
   thiên vị/suy diễn động cơ không, có tôn trọng đúng mực vai trò persona không. LƯU Ý: trình bày
   một sự kiện/tuyên bố dưới dạng câu khẳng định trực tiếp (không kèm "theo nguồn tin", "theo X
   công bố"...) KHÔNG tự nó là thiên vị - đây là cách viết tóm tắt tin tức bình thường, kể cả khi
   nội dung đó là phát ngôn/cáo buộc của một bên. CHỈ fail khi câu văn thực sự chứa nhận định/
   phán xét cá nhân của người viết hoặc suy diễn động cơ không có căn cứ, không phải chỉ vì thiếu
   cụm dẫn nguồn.

QUY TẮC MẶC ĐỊNH KHI CHẤM: đánh giá công bằng, không cần khắt khe với các khác biệt rất nhỏ hoặc
không ảnh hưởng đáng kể tới trải nghiệm đọc. Chỉ kết luận "fail" khi trích dẫn được cụ thể câu/cụm
từ trong bản tóm tắt cho thấy rõ vi phạm; nếu chỉ là cảm nhận chủ quan, chọn "pass".

(bo_cuc_uu_tien - thứ tự nội dung theo ưu tiên và câu dẫn chuyển nhóm - được kiểm chắc chắn bằng
Python riêng ngay sau bước này, không cần bạn chấm.)

CHỈ trả về một đối tượng JSON đúng định dạng sau, không thêm lời dẫn, không dùng markdown, CHỈ 3
khóa, mỗi khóa là MỘT OBJECT có ĐÚNG 2 trường "verdict" và "ly_do":
{{
  "trinh_bay_phu_hop": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "giong_dieu_phu_hop": {{"verdict": "pass hoặc fail", "ly_do": "..."}},
  "thai_do_dung_dan": {{"verdict": "pass hoặc fail", "ly_do": "..."}}
}}
""".strip()

    return prompt


async def _goi_judge(prompt: str, max_tokens: int, client, semaphore, model_name: str,
                      max_tokens_mo_rong: int = None) -> dict:
    async def _goi(mt):
        async def _call():
            return await client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": 0.0,
                    "max_output_tokens": mt,
                    "response_mime_type": "application/json",
                },
            )

        async with semaphore:
            return await retry_generate_async(_call)

    response = await _goi(max_tokens)
    bi_cat_cut = getattr(response, "finish_reason", None) == "length"
    if bi_cat_cut and max_tokens_mo_rong:
        response = await _goi(max_tokens_mo_rong)

    raw = response.text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return {"loi": None, "cham": json.loads(raw)}
    except json.JSONDecodeError:
        return {"loi": "LỖI: không parse được JSON từ judge.", "raw": raw}


async def cham_1_batch_nguon(persona: dict, batch: dict, nguon_g: list, nguon_b: list,
                              client, semaphore, model_name: str = OSS_MODEL_NAME) -> dict:
    nhom_ten = batch.get("nhom_chu_de", "")
    tin_links = batch.get("tin_links", [])
    batch_text = batch.get("text", "")
    nguon_c = lay_noi_dung_nguon_C(tin_links)

    prompt = build_judge_prompt_nguon(persona, nguon_c, nguon_g, nguon_b, batch_text, nhom_ten)
    ket_goi = await _goi_judge(prompt, NGUON_JUDGE_MAX_TOKENS, client, semaphore, model_name,
                               NGUON_JUDGE_MAX_TOKENS_MO_RONG)

    nhan_batch = f"{nhom_ten} ({len(tin_links)} tin)"
    if ket_goi["loi"]:
        return {
            "nhan_batch": nhan_batch,
            "loi": ket_goi["loi"],
            "raw_response": ket_goi["raw"],
        }

    cham = ket_goi["cham"]
    loi_dinh_dang = []
    for tc in TIEU_CHI_CAN_NGUON:
        gt = cham.get(tc)
        if not isinstance(gt, dict) or "verdict" not in gt:
            loi_dinh_dang.append(tc)
            cham[tc] = {
                "verdict": "fail",
                "ly_do": "LỖI ĐỊNH DẠNG: judge trả về sai cấu trúc cho tiêu chí này, mặc định fail.",
            }

    hau_kiem = hau_kiem_fail_reasons_batch(nhan_batch, cham, batch_text, nguon_c, nguon_g, nguon_b)

    for tc in hau_kiem["tc_bi_bia"]:
        ly_do_goc = cham[tc].get("ly_do", "")
        cham[tc]["verdict"] = "pass"
        cham[tc]["ly_do"] = (
            f"[TỰ ĐỘNG LẬT VERDICT] Judge kết luận fail nhưng toàn bộ trích dẫn làm bằng chứng đều "
            f"không có trong nguồn/thân bài (bịa hoặc suy diễn) - coi như không có căn cứ hợp lệ, "
            f"chuyển sang pass. Lý do gốc của judge: {ly_do_goc}"
        )

    return {
        "nhan_batch": nhan_batch,
        "loi": None,
        "cham": cham,
        "loi_dinh_dang": loi_dinh_dang,
        "hau_kiem_canh_bao": hau_kiem["chi_tiet_canh_bao"] if hau_kiem["can_soat_tay"] else [],
    }

async def cham_hinh_thuc(persona: dict, summary: str, than_bai_text: str, cac_batch: list, ten_cac_nhom: list, day_du: bool,
                          client, semaphore, model_name: str = OSS_MODEL_NAME) -> dict:
    # bo_cuc_uu_tien tính 100% bằng Python - tính TRƯỚC, độc lập, để không bị vạ lây khi lời gọi
    # judge cho 3 tiêu chí còn lại bị lỗi mạng/parse JSON.
    vi_pham_bo_cuc = hau_kiem_bo_cuc_uu_tien(cac_batch)
    if vi_pham_bo_cuc:
        bo_cuc_uu_tien_ket_qua = {"verdict": "fail", "ly_do": "[HẬU KIỂM PYTHON] " + " | ".join(vi_pham_bo_cuc)}
    else:
        bo_cuc_uu_tien_ket_qua = {
            "verdict": "pass",
            "ly_do": "[HẬU KIỂM PYTHON] Mọi lần chuyển nhóm chủ đề đều có tên nhóm ở đầu đoạn; thứ tự ưu tiên do pipeline đảm bảo.",
        }

    prompt = build_judge_prompt_hinh_thuc(persona, summary, ten_cac_nhom, day_du)
    ket_goi = await _goi_judge(prompt, HINH_THUC_JUDGE_MAX_TOKENS, client, semaphore, model_name, HINH_THUC_JUDGE_MAX_TOKENS_MO_RONG)

    if ket_goi["loi"]:
        return {
            "loi": ket_goi["loi"],
            "raw_response": ket_goi["raw"],
            "cham_bo_cuc_rieng": bo_cuc_uu_tien_ket_qua,
        }

    cham = ket_goi["cham"]
    loi_dinh_dang = []
    for tc in TIEU_CHI_HINH_THUC:
        if tc == "bo_cuc_uu_tien":
            continue
        gt = cham.get(tc)
        if not isinstance(gt, dict) or "verdict" not in gt:
            loi_dinh_dang.append(tc)
            cham[tc] = {
                "verdict": "fail",
                "ly_do": "LỖI ĐỊNH DẠNG: judge trả về sai cấu trúc cho tiêu chí này, mặc định fail.",
            }

    cham["bo_cuc_uu_tien"] = bo_cuc_uu_tien_ket_qua

    cum_cam_con_sot = hau_kiem_cum_tu_cam(than_bai_text)
    if cum_cam_con_sot:
        ly_do_judge_goc = cham.get("trinh_bay_phu_hop", {}).get("ly_do", "")
        cham["trinh_bay_phu_hop"] = {
            "verdict": "fail",
            "ly_do": (
                f"[HẬU KIỂM TỰ ĐỘNG - GHI ĐÈ] Phát hiện cụm cấm dùng làm câu mở đầu trong thân bài: "
                f"{'; '.join(cum_cam_con_sot)}. Lý do judge gốc (nếu có): {ly_do_judge_goc}"
            ),
        }

    cham, canh_bao_hallucination = hau_kiem_hallucination_hinh_thuc(cham, summary)
    cham, canh_bao_mien_chuyen_sau = hau_kiem_mien_chuyen_sau(cham, summary, than_bai_text, cac_batch)

    return {
        "loi": None,
        "cham": cham,
        "loi_dinh_dang": loi_dinh_dang,
        "hau_kiem_canh_bao": canh_bao_hallucination + canh_bao_mien_chuyen_sau,
    }

async def cham_1_persona(persona: dict, ket_qua_rss: dict, index_theo_link: dict, index_theo_title: dict,
                          client, semaphore, model_name: str = OSS_MODEL_NAME) -> dict:
    summary = ket_qua_rss.get("summary", "")
    if not summary:
        return {
            "id": persona.get("id"),
            "note": "Bỏ qua đánh giá - bản tóm tắt rỗng (không có tin khớp chu_de).",
        }

    cac_batch = ket_qua_rss.get("than_bai_theo_batch")
    if not cac_batch:
        return {
            "id": persona.get("id"),
            "note": (
                "Bỏ qua đánh giá - kết quả rss_personalize này KHÔNG có field 'than_bai_theo_batch' "
                "(có thể được sinh bằng bản rss_personalize.py cũ hơn bản đang dùng) - cần chạy lại "
                "rss_personalize cho persona này trước khi đánh giá."
            ),
        }

    nguon_g, thieu_g = lay_noi_dung_nguon_GB(
        ket_qua_rss.get("tin_gian_tiep", []), index_theo_link, index_theo_title
    )
    nguon_b, thieu_b = lay_noi_dung_nguon_GB(
        ket_qua_rss.get("bai_lien_quan", []), index_theo_link, index_theo_title
    )

    # --- Chấm chon_loc_phu_hop + nhat_quan theo TỪNG batch, song song ---
    ket_qua_batch = await asyncio.gather(*[
        cham_1_batch_nguon(persona, batch, nguon_g, nguon_b, client, semaphore, model_name)
        for batch in cac_batch
    ])

    # --- Chấm 4 tiêu chí hình thức, 1 lần ---
    so_bai_moi_nhom = ket_qua_rss.get("so_bai_moi_nhom", [])
    ten_cac_nhom = [n.get("chu_de", "") for n in so_bai_moi_nhom]
    day_du = ket_qua_rss.get("day_du")
    if day_du is None:
        day_du = summary.strip().split("\n\n")[0].strip().lower().startswith("về ") is False
    than_bai_text = "\n\n".join(b.get("text", "") for b in cac_batch)
    ket_qua_hinh_thuc = await cham_hinh_thuc(persona, summary, than_bai_text, cac_batch, ten_cac_nhom, day_du, client,
                                             semaphore, model_name)

    cham_tong = {}
    canh_bao_loi_dinh_dang = []
    canh_bao_thieu_batch = []
    hau_kiem_tong = []

    for tc in TIEU_CHI_CAN_NGUON:
        cac_verdict = []
        cac_ly_do_fail = []
        cac_ly_do_pass = []
        for kb in ket_qua_batch:
            if kb.get("loi"):
                canh_bao_thieu_batch.append(f"[{kb.get('nhan_batch', '?')}] {kb['loi']}")
                continue
            ket_tc = kb["cham"].get(tc, {})
            v = ket_tc.get("verdict", "fail")
            ly_do_batch = ket_tc.get("ly_do", "")
            cac_verdict.append(v)
            (cac_ly_do_fail if v == "fail" else cac_ly_do_pass).append(f"[{kb['nhan_batch']}] {ly_do_batch}")
            if kb.get("loi_dinh_dang") and tc in kb["loi_dinh_dang"]:
                canh_bao_loi_dinh_dang.append(f"{tc} (batch {kb['nhan_batch']})")
            hau_kiem_tong.extend(kb.get("hau_kiem_canh_bao", []))

        if not cac_verdict:
            cham_tong[tc] = {"verdict": "fail", "ly_do": "Không có batch nào chấm được - xem canh_bao_thieu_batch."}
        else:
            tong = len(cac_verdict)
            so_pass = sum(1 for v in cac_verdict if v == "pass")
            # Ngưỡng % quá thô với tong nhỏ (3/4=75%<80% vẫn fail oan) -> đổi sang cho phép fail
            # tối đa N batch theo số đếm; tong<=2 thì không cho phép miss (mẫu quá ít để nới lỏng).
            so_fail_cho_phep = 0 if tong <= 2 else max(1, round(tong * (1 - NGUONG_TI_LE_PASS_BATCH)))
            if so_pass >= tong - so_fail_cho_phep:
                ly_do = f"Đạt {so_pass}/{tong} batch (cho phép fail tối đa {so_fail_cho_phep}). "
                ly_do += "Lý do judge: " + " | ".join(cac_ly_do_pass[:3])
                if len(cac_ly_do_pass) > 3:
                    ly_do += f" (và {len(cac_ly_do_pass) - 3} batch khác cũng pass)"
                if cac_ly_do_fail:
                    ly_do += " Batch fail (không ảnh hưởng verdict do trong ngưỡng cho phép): " + " | ".join(
                        cac_ly_do_fail)
                cham_tong[tc] = {"verdict": "pass", "ly_do": ly_do}
            else:
                cham_tong[tc] = {
                    "verdict": "fail",
                    "ly_do": (
                            f"Chỉ đạt {so_pass}/{tong} batch (cho phép fail tối đa {so_fail_cho_phep}): "
                            + " | ".join(cac_ly_do_fail)
                    ),
                }

    if ket_qua_hinh_thuc.get("loi"):
        canh_bao_thieu_batch.append(f"[hình thức] {ket_qua_hinh_thuc['loi']}")
        for tc in TIEU_CHI_HINH_THUC:
            if tc == "bo_cuc_uu_tien" and ket_qua_hinh_thuc.get("cham_bo_cuc_rieng"):
                cham_tong[tc] = ket_qua_hinh_thuc["cham_bo_cuc_rieng"]
            else:
                cham_tong[tc] = {"verdict": "fail", "ly_do": "Không chấm được - xem canh_bao_thieu_batch."}
    else:
        for tc in TIEU_CHI_HINH_THUC:
            cham_tong[tc] = ket_qua_hinh_thuc["cham"].get(tc, {"verdict": "fail", "ly_do": "(thiếu)"})
        if ket_qua_hinh_thuc.get("loi_dinh_dang"):
            canh_bao_loi_dinh_dang.extend(f"{tc} (hình thức)" for tc in ket_qua_hinh_thuc["loi_dinh_dang"])

    hau_kiem_tong.extend(ket_qua_hinh_thuc.get("hau_kiem_canh_bao", []))

    so_dat = sum(1 for tc in TIEU_CHI if cham_tong.get(tc, {}).get("verdict") == "pass")

    ket_qua_cham = {
        "id": persona.get("id"),
        "tieu_chi": cham_tong,
        "so_tieu_chi_dat": so_dat,
        "verdict_cuoi": "DAT" if so_dat == len(TIEU_CHI) else "KHONG_DAT",
        "so_batch_da_cham_nguon": len(cac_batch),
    }
    if canh_bao_loi_dinh_dang:
        ket_qua_cham["canh_bao_loi_dinh_dang"] = (
            f"Các tiêu chí bị judge trả sai định dạng (đã mặc định fail): "
            f"{', '.join(canh_bao_loi_dinh_dang)}."
        )
    if canh_bao_thieu_batch:
        ket_qua_cham["canh_bao_loi_goi_judge"] = canh_bao_thieu_batch
    if thieu_g + thieu_b > 0:
        ket_qua_cham["canh_bao_thieu_nguon"] = (
            f"{thieu_g + thieu_b} tin gián tiếp/bài góc nhìn không khớp được với văn bản nguồn "
            f"(chỉ còn tiêu đề) - kết quả chấm có thể KHÔNG ĐÁNG TIN CẬY cho phần đó."
        )
    if hau_kiem_tong:
        ket_qua_cham["can_soat_tay"] = True
        ket_qua_cham["hau_kiem_canh_bao"] = hau_kiem_tong

    return ket_qua_cham


def in_ket_qua_cham(persona_id: str, cham: dict) -> None:
    verdict = cham.get("verdict_cuoi")
    if verdict == "DAT":
        print(f" [{persona_id}] ĐẠT cả 6 tiêu chí.")
    elif verdict == "KHONG_DAT":
        fail_list = [
            tc for tc in TIEU_CHI
            if cham.get("tieu_chi", {}).get(tc, {}).get("verdict") == "fail"
        ]
        print(f" [{persona_id}] Phát hiện fail — rớt {len(fail_list)}/6 tiêu chí: {', '.join(fail_list)}")
    else:
        print(f" [{persona_id}] bỏ qua chấm — {cham.get('note', 'không rõ lý do')}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Đánh giá bản tóm tắt RSS bằng LLM Judge (OSS)")
    parser.add_argument("--id", type=str, help="id của persona, ví dụ NN0001 (không dùng chung với --data-dir)")
    parser.add_argument("-n", "--so-luong", type=int, help="Chỉ đánh giá N kết quả đầu tiên (áp dụng cho MỖI file nếu dùng --data-dir)")
    parser.add_argument("--variant", type=str, default=None,
                        help="ten bien the persona, neu co se doc/ghi vao thu muc con rieng")
    parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        help=(
            "File dữ liệu bài viết TƯƠNG ỨNG với lần chạy rss_personalize.py muốn chấm (mặc định "
            "vnexpress_rss_snapshot_3007.json). Không dùng chung với --data-dir."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help=(
            "Thư mục chứa nhiều file .jsonl TƯƠNG ỨNG với lần chạy rss_personalize.py --data-dir "
            "muốn chấm (vd theodongsukien1). Chấm lần lượt từng file, đọc/ghi đúng thư mục con "
            "tương ứng đã dùng khi personalize. Không dùng chung với --data-file."
        ),
    )
    args = parser.parse_args()

    if args.data_file and args.data_dir:
        raise SystemExit("Chỉ chọn 1 trong 2: --data-file hoặc --data-dir, không dùng cùng lúc.")
    if args.data_dir and args.id:
        raise SystemExit("--id chỉ dùng để test 1 persona trên 1 file, không dùng chung với --data-dir.")

    personas = load_personas(args.variant)
    persona_index = {p["id"]: p for p in personas}


    def _resolve_data_dir(raw: str) -> Path:
        p = Path(raw)
        if p.exists():
            return p
        p2 = DATA_DIR / raw
        if p2.exists():
            return p2
        raise SystemExit(f"Không tìm thấy thư mục data: {raw}")


    async def cham_1_file(duong_dan_data, JSON_DIR, EVAL_DIR, client, semaphore):
        if not JSON_DIR.exists():
            print(f"[{duong_dan_data.name}] chưa có kết quả rss_personalize ở {JSON_DIR}, bỏ qua.")
            return
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        index_theo_link, index_theo_title = load_articles_index(duong_dan_data)

        print(f"\n=== Chấm file: {duong_dan_data.name} ===")

        if args.id:
            json_path = JSON_DIR / f"{args.id}.json"
            if not json_path.exists():
                raise SystemExit(f"Không tìm thấy kết quả rss_personalize cho id = {args.id} trong {JSON_DIR}")
            with open(json_path, encoding="utf-8") as f:
                ket_qua_rss = json.load(f)
            persona = persona_index.get(args.id)
            if persona is None:
                raise SystemExit(f"Không tìm thấy persona có id = {args.id}")

            print(f"[{args.id}] đang chấm...")
            cham = await cham_1_persona(persona, ket_qua_rss, index_theo_link, index_theo_title, client, semaphore)

            out_path = EVAL_DIR / f"{args.id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(cham, f, ensure_ascii=False, indent=2)
            in_ket_qua_cham(args.id, cham)
            if cham.get("can_soat_tay"):
                print(f" [{args.id}] có {len(cham['hau_kiem_canh_bao'])} cảnh báo hậu kiểm - cần soát tay:")
                for cb in cham["hau_kiem_canh_bao"]:
                    print(f"      - {cb}")
            return

        danh_sach_file = sorted(JSON_DIR.glob("*.json"))
        if args.so_luong:
            danh_sach_file = danh_sach_file[:args.so_luong]

        print("Tổng số kết quả cần chấm:", len(danh_sach_file))
        t_bat_dau = time.time()
        ket_qua_tong = {"dat": 0, "khong_dat": 0, "bo_qua": 0}

        async def xu_ly_mot_file(json_path):
            persona_id = json_path.stem
            out_path = EVAL_DIR / f"{persona_id}.json"
            if out_path.exists():
                print(f"[{persona_id}] đã chấm rồi, bỏ qua.")
                return
            persona = persona_index.get(persona_id)
            if persona is None:
                print(f"[{persona_id}] không tìm thấy persona tương ứng, bỏ qua.")
                return

            with open(json_path, encoding="utf-8") as f:
                ket_qua_rss = json.load(f)
            print(f"[{persona_id}] đang chấm...")
            cham = await cham_1_persona(persona, ket_qua_rss, index_theo_link, index_theo_title, client, semaphore)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(cham, f, ensure_ascii=False, indent=2)
            in_ket_qua_cham(persona_id, cham)

            if cham.get("verdict_cuoi") == "DAT":
                ket_qua_tong["dat"] += 1
            elif cham.get("verdict_cuoi") == "KHONG_DAT":
                ket_qua_tong["khong_dat"] += 1
            else:
                ket_qua_tong["bo_qua"] += 1

        tasks = [xu_ly_mot_file(jp) for jp in danh_sach_file]
        await asyncio.gather(*tasks)

        print(f"Xong file {duong_dan_data.name}. Thời gian:", round((time.time() - t_bat_dau) / 60, 1), "phút")
        print(f"ĐẠT cả 6 tiêu chí: {ket_qua_tong['dat']}")
        print(f"KHÔNG ĐẠT (thiếu ít nhất 1 tiêu chí): {ket_qua_tong['khong_dat']}")
        print(f"Bỏ qua (rỗng/lỗi/không có persona): {ket_qua_tong['bo_qua']}")


    async def chay():
        client = tao_oss_client_async()
        semaphore = asyncio.Semaphore(OSS_MAX_CONCURRENCY_SUMMARY)

        if args.data_dir:
            thu_muc_data = _resolve_data_dir(args.data_dir)
            ten_nguon = thu_muc_data.name
            danh_sach_file = sorted(thu_muc_data.glob("*.jsonl"))
            if not danh_sach_file:
                raise SystemExit(f"Không tìm thấy file .jsonl nào trong {thu_muc_data}")
            print(f"Tìm thấy {len(danh_sach_file)} file .jsonl trong {thu_muc_data}, sẽ chấm LẦN LƯỢT từng file.")

            ten_bien_the = args.variant or "nt_nn_tc_kn_cd_ch"
            for duong_dan_data in danh_sach_file:
                base = OUTPUT_DIR / ten_nguon / duong_dan_data.stem
                JSON_DIR = base / "json" / ten_bien_the
                EVAL_DIR = base / "eval" / ten_bien_the
                await cham_1_file(duong_dan_data, JSON_DIR, EVAL_DIR, client, semaphore)
        else:
            duong_dan_data = Path(args.data_file) if args.data_file else (DATA_DIR / "vnexpress_rss_snapshot_3007.json")

            if args.variant:
                JSON_DIR = OUTPUT_DIR / "snapshot" / "json" / args.variant
                EVAL_DIR = OUTPUT_DIR / "snapshot" / "eval" / args.variant
            else:
                JSON_DIR = OUTPUT_DIR / "snapshot" / "json"
                EVAL_DIR = OUTPUT_DIR / "snapshot" / "eval"

            await cham_1_file(duong_dan_data, JSON_DIR, EVAL_DIR, client, semaphore)

    asyncio.run(chay())