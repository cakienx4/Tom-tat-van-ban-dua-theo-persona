"""
pipeline/rss/evaluate_rss_summary_gemini.py

Buoc 4 - Danh gia ban tom tat RSS ca nhan hoa bang LLM Judge (Gemini),
theo khung 6 tieu chi: chon_loc_phu_hop, nhat_quan, trinh_bay_phu_hop,
bo_cuc_uu_tien, giong_dieu_phu_hop, thai_do_dung_dan.

Doc file ket qua .json da sinh boi rss_personalize.py (khong doc .md,
vi .json co san ranked_articles/tin_gian_tiep de tra nguoc ve van ban nguon).
"""

import os
import json
import time
from collections import Counter
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


def lay_noi_dung_nguon(ranked_items: list, index_theo_link: dict, index_theo_title: dict,
                       dung_full_content: bool = True) -> tuple:
    """
    Voi moi item, thu tra theo link truoc, khong khop thi thu theo title.
    Uu tien lay noi dung day du (content), fallback ve summary (teaser ngan)
    neu bai khong co content. Tra ve (danh_sach_noi_dung, so_bai_khong_tim_thay).
    dung_full_content=False -> chi lay summary (teaser). Dung cho tin gian tiep, vi
    rss_personalize chi dua summary cho model o nhom nay; judge khong duoc thay nhieu hon
    model da thay, neu khong se bi chan "bo sot" chi tiet model khong he co.
    """
    ket_qua = []
    so_khong_tim_thay = 0
    for item in ranked_items:
        goc = index_theo_link.get(item.get("link")) or index_theo_title.get(item.get("title"))
        if goc:
            if dung_full_content:
                noi_dung = goc.get("content") or goc.get("summary", "")
            else:
                noi_dung = goc.get("summary", "")
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

def _format_nguon(nguon_list: list, nhan: str, prefix: str) -> str:
    if not nguon_list:
        return f"{nhan}: (không có)"
    dong = [f"{nhan}:"]
    for i, n in enumerate(nguon_list, 1):
        dong.append(f"{prefix}{i}. [{n['genre']}] {n['title']}\n{n['noi_dung']}")
    return "\n".join(dong)

import re


def _trich_cac_doan_trich_dan(text: str) -> list:
    """Tìm tất cả cụm được đặt trong dấu ngoặc kép (kiểu " " hoặc “ ”) trong ly_do."""
    ket_qua = []
    ket_qua.extend(re.findall(r'"([^"]{5,})"', text))
    ket_qua.extend(re.findall(r'“([^”]{5,})”', text))
    return ket_qua


def _chuan_hoa(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def hau_kiem_fail_reasons(cham: dict, summary: str, nguon_chinh: list, nguon_gian_tiep: list) -> dict:
    """
    Kiểm tra bán tự động (không dùng LLM) các lý do "fail" judge đưa ra, nhằm phát hiện
    trường hợp judge trích dẫn sai hoặc bịa nội dung không có thật. KHÔNG tự đảo verdict,
    chỉ gắn cờ để soát tay - vì bản thân logic tự động này cũng có thể có false positive
    (ví dụ judge diễn giải lại thay vì trích nguyên văn 100%).
    """
    canh_bao = []
    summary_chuan = _chuan_hoa(summary)
    nguon_text_chuan = _chuan_hoa(
        " ".join((n.get("noi_dung", "") + " " + n.get("title", "")) for n in nguon_chinh + nguon_gian_tiep)
    )
    so_c, so_g = len(nguon_chinh), len(nguon_gian_tiep)

    for tc, ket in cham.items():
        if not isinstance(ket, dict) or ket.get("verdict") != "fail":
            continue
        ly_do = ket.get("ly_do", "")

        # 1. Mã tin C../G.. được trích dẫn có thực sự tồn tại không
        for tien_to, so_str in re.findall(r"\b([CG])(\d+)\b", ly_do):
            so = int(so_str)
            if tien_to == "C" and so > so_c:
                canh_bao.append(f"[{tc}] trích mã C{so} không tồn tại (nhóm chính chỉ có {so_c} tin).")
            if tien_to == "G" and so > so_g:
                canh_bao.append(f"[{tc}] trích mã G{so} không tồn tại (nhóm gián tiếp chỉ có {so_g} tin).")

        # 2. Trích dẫn "nguyên văn" từ bản tóm tắt có thực sự xuất hiện trong bản tóm tắt không
        for trich in _trich_cac_doan_trich_dan(ly_do):
            if _chuan_hoa(trich) not in summary_chuan:
                canh_bao.append(
                    f"[{tc}] trích dẫn \"{trich[:60]}...\" KHÔNG có trong bản tóm tắt - "
                    f"có khả năng judge bịa nội dung."
                )

        # 3. Khẳng định "bỏ sót" một nội dung cụ thể - kiểm tra nội dung đó có tồn tại
        #    trong văn bản nguồn hay không
        if any(tu in ly_do.lower() for tu in ["bỏ sót", "bỏ qua", "thiếu nội dung", "không đề cập"]):
            for trich in _trich_cac_doan_trich_dan(ly_do):
                trich_chuan = _chuan_hoa(trich)
                if trich_chuan and trich_chuan not in nguon_text_chuan:
                    canh_bao.append(
                        f"[{tc}] cho rằng bản tóm tắt bỏ sót \"{trich[:60]}...\" nhưng nội dung này "
                        f"KHÔNG tìm thấy trong văn bản nguồn - có khả năng judge suy diễn nội dung "
                        f"không tồn tại."
                    )

    # 4. Cáo buộc "gộp đoạn": kiểm tra tính nhất quán nội tại của lý do
    doan_list = _tach_doan_van(summary)
    for tc, ket in cham.items():
        if not isinstance(ket, dict) or ket.get("verdict") != "fail":
            continue
        ly_do = ket.get("ly_do", "")
        if not any(tu in ly_do.lower() for tu in ["gộp", "cùng một đoạn", "cùng 1 đoạn"]):
            continue
        ma_tin = set(re.findall(r"\b([CG]\d+)\b", ly_do))
        if len(ma_tin) < 2:
            canh_bao.append(
                f"[{tc}] cáo buộc gộp đoạn nhưng chỉ nêu {len(ma_tin)} mã tin "
                f"({', '.join(sorted(ma_tin)) or 'không có'}) cho 2 nội dung khác nhau - nhiều khả năng "
                f"judge nhầm mã tin (ví dụ C11/C12), cần soát tay đoạn được trích."
            )
        for so_doan in re.findall(r"ĐOẠN\s*(\d+)", ly_do):
            if int(so_doan) > len(doan_list):
                canh_bao.append(
                    f"[{tc}] trích [ĐOẠN {so_doan}] nhưng bản tóm tắt chỉ có {len(doan_list)} đoạn."
                )

    return {"can_soat_tay": bool(canh_bao), "chi_tiet_canh_bao": canh_bao}

def _tach_doan_van(summary: str) -> list:
    return [d.strip() for d in re.split(r"\n\s*\n", summary) if d.strip()]


def _dinh_dang_doan_van(doan_list: list) -> str:
    return "\n\n".join(f"[ĐOẠN {i}]\n{d}" for i, d in enumerate(doan_list, 1))

def _nhom_chu_de_chinh(nguon_chinh: list) -> list:
    """Gom cac tin C lien tiep cung genre thanh nhom (ranked_articles da xep theo thu tu chu_de).
    Tra ve [(genre, [ma_tin C..]), ...]."""
    nhom = []
    for i, n in enumerate(nguon_chinh, 1):
        if nhom and nhom[-1][0] == n.get("genre"):
            nhom[-1][1].append(f"C{i}")
        else:
            nhom.append((n.get("genre"), [f"C{i}"]))
    return nhom


def _mo_ta_kiem_tra_chuyen_nhom(nguon_chinh: list) -> str:
    nhom = _nhom_chu_de_chinh(nguon_chinh)
    if len(nhom) < 2:
        return (
            "KIỂM TRA CHUYỂN NHÓM: bản tóm tắt này chỉ có 1 nhóm chủ đề chính nên KHÔNG có lần "
            "chuyển nhóm nào — TUYỆT ĐỐI không được chấm fail bo_cuc_uu_tien vì lý do thiếu câu dẫn "
            "chuyển nhóm."
        )
    dong_nhom = "\n".join(
        f"- Nhóm {i}: {g} ({ds[0]}–{ds[-1]})" if len(ds) > 1 else f"- Nhóm {i}: {g} ({ds[0]})"
        for i, (g, ds) in enumerate(nhom, 1)
    )
    dong_can_dan = "; ".join(
        f"đoạn tin của {ds[0]} (đầu nhóm {i}: {g})" for i, (g, ds) in enumerate(nhom[1:], 2)
    )
    return f"""KIỂM TRA CHUYỂN NHÓM (cấu trúc nhóm dưới đây được tính TỰ ĐỘNG từ dữ liệu — đây là NGUỒN DUY
NHẤT xác định ranh giới nhóm; KHÔNG dựa vào danh sách "Chủ đề quan tâm" trong hồ sơ vì hôm đó có
thể không có tin cho một số chủ đề):
{dong_nhom}
Số lần chuyển nhóm cần có câu dẫn: {len(nhom) - 1}, đặt ở đầu {dong_can_dan}. Nhóm đầu tiên KHÔNG
cần câu dẫn. Câu dẫn hợp lệ là một câu ngắn ở đầu đoạn tin đầu tiên của nhóm mới, nêu tên hoặc chủ
đề của nhóm đó — không bắt buộc đúng cụm "Chuyển sang nhóm". Việc chuyển sang nhóm tin gián tiếp (G)
KHÔNG tính là chuyển nhóm chính. Chỉ kết luận thiếu câu dẫn khi bạn trích nguyên văn được câu đầu
của đoạn tin đầu tiên của nhóm mới và câu đó thật sự không nêu chủ đề nhóm; khi đó bo_cuc_uu_tien
"fail"."""


def build_judge_prompt(persona: dict, nguon_chinh: list, nguon_gian_tiep: list, summary: str,
                        thong_ke: dict) -> str:
    ho_so = f"""
Vai trò: {persona.get('kinh_nghiem', '')}
Đơn vị công tác: {persona.get('to_chuc', '')}
Ngành: {persona.get('nganh_to', '')} - {persona.get('nganh_nho', '')}
Chủ đề quan tâm (ưu tiên từ cao xuống thấp): {', '.join(persona.get('chu_de', []))}
Khuynh hướng/mối quan tâm trước mắt: {persona.get('cau_hoi_truoc_mat', '')}
Mô tả chung: {persona.get('mo_ta_chung', '')}
""".strip()

    nguon_text = (
        _format_nguon(nguon_chinh, "VĂN BẢN NGUỒN - nhóm tin chính (đúng chu_de persona)", "C")
        + "\n\n"
        + _format_nguon(nguon_gian_tiep, "VĂN BẢN NGUỒN - nhóm tin liên quan gián tiếp", "G")
    )

    ghi_chu_danh_so = """
LƯU Ý QUAN TRỌNG VỀ ĐÁNH SỐ: hai danh sách trên đánh số ĐỘC LẬP với 2 tiền tố khác nhau — "C1,
C2..." cho nhóm tin chính, "G1, G2..." cho nhóm tin gián tiếp. LUÔN dùng đúng tiền tố khi trích
dẫn trong ly_do (ví dụ "C4", không viết trống "tin 4"), để tránh nhầm lẫn hai danh sách. Tin
gián tiếp (G) được PHÉP bị lược bỏ hoàn toàn khỏi bản tóm tắt nếu ít giá trị — KHÔNG được coi
việc thiếu một tin G nào đó là lỗi chon_loc_phu_hop hay trinh_bay_phu_hop; chỉ tin nhóm chính
(C) mới bắt buộc đủ 1 tin - 1 đoạn.
""".strip()

    canh_bao_it_tin = ""
    if thong_ke.get("so_tin_chinh", 0) == 0:
        canh_bao_it_tin = f"""
    - CẢNH BÁO ĐẶC BIỆT: nhóm tin chính (đúng chu_de chuyên môn của persona) KHÔNG CÓ tin nào đạt
      ngưỡng phù hợp trong đợt tin này. Đây là tình huống hợp lệ do dữ liệu ngày hôm đó không có tin
      đúng chuyên môn, KHÔNG phải lỗi của bước sinh bài. Trong trường hợp này, việc bản tóm tắt dùng
      các tin thuộc nhóm gián tiếp có genre trùng với chu_de persona làm nội dung chính thay thế là
      cách xử lý ĐÚNG và nên được chấm "pass" cho chon_loc_phu_hop nếu các tin đó thực sự là lựa
      chọn phù hợp nhất trong số các tin gián tiếp hiện có — KHÔNG được yêu cầu bản tóm tắt phải có
      nội dung "đúng chuyên môn hơn" nếu nội dung đó không tồn tại trong nguồn đã cho.
    """

    thong_ke_text = f"""
    THỐNG KÊ CƠ HỌC (tính tự động, không phải cảm nhận của giám khảo):
    - Số tin trong nhóm chính (BẮT BUỘC mỗi tin 1 đoạn riêng trong phần THÂN BÀI): {thong_ke.get('so_tin_chinh')}
    - Tổng số đoạn văn thực tế đếm được trong TOÀN BỘ bản tóm tắt (kể cả mở bài, kết luận, tin
      gián tiếp): {thong_ke.get('so_doan_thuc_te')}
    - LƯU Ý: con số này CAO HƠN số tin nhóm chính là BÌNH THƯỜNG, vì nó còn gồm dòng tiêu đề
      (nếu có), đoạn mở bài, đoạn kết luận và các đoạn tin gián tiếp. Chỉ nên nghi ngờ gộp đoạn khi
      số đoạn thân bài ÍT HƠN số tin nhóm chính, và khi đó vẫn phải chứng minh bằng [ĐOẠN n] cụ thể.
    {canh_bao_it_tin}- Ghi chú từ bước sinh bài (nếu có): {thong_ke.get('note') or '(không có)'}
    """.strip()

    doan_list = _tach_doan_van(summary)
    doan_van_text = _dinh_dang_doan_van(doan_list)
    kiem_tra_chuyen_nhom = _mo_ta_kiem_tra_chuyen_nhom(nguon_chinh)

    prompt = f"""
Bạn là giám khảo đánh giá bản tóm tắt tin tức cá nhân hóa theo persona công chức/nhà nước.

HỒ SƠ PERSONA:
{ho_so}

{nguon_text}

{ghi_chu_danh_so}

{thong_ke_text}

BẢN TÓM TẮT CẦN CHẤM (đã được TÁCH SẴN thành {len(doan_list)} đoạn văn theo đúng dấu xuống dòng
trống trong văn bản gốc, đánh số [ĐOẠN 1], [ĐOẠN 2]... — đây là ranh giới đoạn CHÍNH XÁC, không
cần tự suy đoán):
{doan_van_text}

BƯỚC BẮT BUỘC TRƯỚC KHI CHẤM (chỉ để bạn tự suy luận, KHÔNG in ra kết quả): với MỖI tin C1,
C2... trong nhóm chính, xác định nó khớp với [ĐOẠN mấy] trong danh sách đã đánh số ở trên (dùng
đúng số đoạn đã cho, KHÔNG tự chia lại đoạn theo cách đọc riêng của bạn). Nếu 2 tin khớp với
CÙNG một số [ĐOẠN], đó là gộp đoạn thật — trích rõ số đoạn đó làm bằng chứng. Nếu 2 tin khớp với
2 số [ĐOẠN] khác nhau (kể cả liền kề, kể cả không có câu "Chuyển sang nhóm..." ở giữa vì cùng
nhóm chủ đề thì không cần câu đó), thì đó KHÔNG phải lỗi gộp — không được kết luận fail.

Khi liệt kê từng tin C1, C2... và đối chiếu với đoạn thân bài tương ứng, hãy làm theo thứ tự:
với MỖI tin C, tìm đúng MỘT đoạn văn trong bản tóm tắt có nội dung khớp với tin đó, và ghi nhận
vị trí đoạn đó (đoạn thứ mấy tính từ đầu thân bài). Nếu 2 tin liên tiếp trỏ tới cùng một vị trí
đoạn, đó mới là gộp thật; nếu chúng trỏ tới 2 đoạn khác nhau (dù liền kề nhau), đó KHÔNG phải
là lỗi gộp.

{kiem_tra_chuyen_nhom}

Chấm bản tóm tắt trên theo đúng 6 tiêu chí sau, mỗi tiêu chí trả về "pass" hoặc "fail"
kèm lý do ngắn gọn (tối đa 2 câu, tiếng Việt có dấu):

1. chon_loc_phu_hop: Bản tóm tắt có ưu tiên chọn chi tiết/dữ kiện liên quan trực tiếp
   đến chu_de và khuynh hướng quan tâm của persona không, có bỏ sót chi tiết quan trọng
   đúng chuyên môn không, có giữ nhiều chi tiết không liên quan không.
   LƯU Ý: mọi tin C đều đã được lọc sẵn và BẮT BUỘC có đoạn riêng, nên việc bản tóm tắt CÓ mặt
   một tin C KHÔNG bị coi là "giữ tin không liên quan"; chỉ xét các chi tiết BÊN TRONG mỗi đoạn.
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
hoặc văn bản nguồn (dùng mã C../G.. khi trích dẫn tin nguồn). Không được viết lý do
chung chung không có dẫn chứng cụ thể.

QUY TẮC TRÍCH DẪN BẮT BUỘC: mọi ly_do khẳng định bản tóm tắt có lỗi (verdict "fail") PHẢI trích
một cụm từ/câu NGẮN thực sự có trong bản tóm tắt làm bằng chứng, đặt trong dấu ngoặc kép, kèm mã
tin (C.. hoặc G..) tương ứng nếu liên quan đến một tin cụ thể. Nếu không thể trích dẫn cụ thể
như vậy, KHÔNG được kết luận "fail" cho tiêu chí đó — chuyển sang "pass".

QUY TẮC RIÊNG CHO CÁO BUỘC "GỘP ĐOẠN" HOẶC "BỎ SÓT TIN": nếu ly_do khẳng định có tin bị gộp
chung đoạn với tin khác (ví dụ "gộp C3 và C4 vào cùng một đoạn"), BẮT BUỘC phải trích nguyên
văn đoạn văn đó trong bản tóm tắt và chỉ ra rõ cả hai nội dung của 2 tin cùng xuất hiện trong
đúng đoạn văn đó. Nếu không trích ra được một đoạn văn cụ thể chứa CẢ HAI nội dung, thì KHÔNG
được kết luận có gộp đoạn — phải chuyển sang "pass" cho tiêu chí đó. QUAN TRỌNG: gộp đoạn CHỈ
tính khi HAI MÃ TIN C KHÁC NHAU (ví dụ C11 và C12) cùng khớp một [ĐOẠN]. Một tin nguồn (một mã C)
có thể nhắc đến nhiều bên/doanh nghiệp/nhân vật, và đoạn tóm tắt tin đó nhắc đủ các bên ấy là
ĐÚNG, không phải gộp. Nếu bạn quy hai nội dung trong một đoạn về CÙNG một mã C thì đó KHÔNG phải
gộp — không được fail vì lý do này; hãy đối chiếu với phần nguồn của mã C đó trước khi kết luận.
Tương tự, nếu khẳng định
có tin C.. bị bỏ sót hoàn toàn, phải xác nhận đã rà soát TOÀN BỘ các đoạn trong thân bài (không
chỉ đọc lướt) trước khi kết luận.

QUY TẮC CHỐNG SUY DIỄN NGUỒN KHÔNG TỒN TẠI: nếu ly_do phê bình bản tóm tắt "bỏ sót" một chủ
đề/nội dung nào đó, BẮT BUỘC phải chỉ ra đúng mã tin (C.. hoặc G..) trong hai danh sách VĂN BẢN
NGUỒN đã cho ở trên có chứa đúng nội dung bị cho là bỏ sót đó. Nếu rà soát toàn bộ danh sách
nguồn mà KHÔNG tìm thấy tin nào khớp, thì đây là suy diễn sai — TUYỆT ĐỐI không được dùng làm lý
do fail. Hồ sơ persona (chu_de, khuynh hướng, mô tả) chỉ mô tả MỐI QUAN TÂM của người đọc, KHÔNG
đảm bảo rằng ngày hôm đó có tin tức thực tế đúng mối quan tâm đó — bản tóm tắt chỉ có thể tóm
tắt những gì THỰC SỰ tồn tại trong hai danh sách nguồn đã cho, không hơn.

QUY TẮC MẶC ĐỊNH KHI CHẤM: bạn PHẢI đóng vai giám khảo khó tính. Nếu phân vân giữa "pass" và
"fail" ở bất kỳ tiêu chí nào, LUÔN chọn "fail" — "pass" chỉ được chọn khi có bằng chứng rõ ràng,
cụ thể, không có ngoại lệ đáng ngờ nào. Không được chấm "pass" chỉ vì văn phong trôi chảy hoặc
"đọc có vẻ ổn" — phải đối chiếu với văn bản nguồn và hồ sơ persona ở TỪNG câu quan trọng.

CHỈ trả về một đối tượng JSON đúng định dạng sau, không thêm lời dẫn, không dùng markdown.
Bước đối chiếu ở trên bạn PHẢI tự thực hiện trong suy luận nội bộ để xác định verdict và viết
ly_do cho chính xác, nhưng TUYỆT ĐỐI KHÔNG in danh sách đối chiếu đó ra trong kết quả trả về.
Kết quả JSON CHỈ được chứa ĐÚNG 6 khóa (chon_loc_phu_hop, nhat_quan, trinh_bay_phu_hop,
bo_cuc_uu_tien, giong_dieu_phu_hop, thai_do_dung_dan), mỗi khóa là MỘT OBJECT có ĐÚNG 2 trường
"verdict" và "ly_do" — không thêm khóa nào khác, không có khóa nào mang giá trị mảng/list:
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
    nguon_gian_tiep, thieu_2 = lay_noi_dung_nguon(
        ket_qua_rss.get("tin_gian_tiep", []), index_theo_link, index_theo_title, dung_full_content=False
    )
    tong_bai = len(ket_qua_rss.get("ranked_articles", [])) + len(ket_qua_rss.get("tin_gian_tiep", []))
    tong_thieu = thieu_1 + thieu_2

    # note cua buoc sinh bai co lan cac "CẢNH BÁO" heuristic (bo sot, thieu doan...) - de nguoi
    # soat tay; KHONG dua sang judge vi se mom san ket luan "fail". Chi giu note thong tin.
    note_cho_judge = " | ".join(
        p for p in (ket_qua_rss.get("note") or "").split(" | ") if p and not p.startswith("CẢNH BÁO")
    )
    thong_ke = {
        "so_tin_chinh": len(ket_qua_rss.get("ranked_articles", [])),
        "so_doan_thuc_te": ket_qua_rss.get("so_doan_thuc_te"),
        "note": note_cho_judge,
    }
    prompt = build_judge_prompt(persona, nguon_chinh, nguon_gian_tiep, summary, thong_ke)

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

    loi_dinh_dang = []
    for tc in TIEU_CHI:
        gt = cham.get(tc)
        if not isinstance(gt, dict) or "verdict" not in gt:
            loi_dinh_dang.append(tc)
            cham[tc] = {
                "verdict": "fail",
                "ly_do": "LỖI ĐỊNH DẠNG: judge trả về sai cấu trúc cho tiêu chí này, mặc định fail.",
            }

    so_dat = sum(1 for tc in TIEU_CHI if cham.get(tc, {}).get("verdict") == "pass")

    ket_qua_cham = {
        "id": persona.get("id"),
        "tieu_chi": cham,
        "so_tieu_chi_dat": so_dat,
        "verdict_cuoi": "DAT" if so_dat == len(TIEU_CHI) else "KHONG_DAT",
    }
    hau_kiem = hau_kiem_fail_reasons(cham, summary, nguon_chinh, nguon_gian_tiep)
    ket_qua_cham["can_soat_tay"] = hau_kiem["can_soat_tay"]
    ket_qua_cham["hau_kiem_canh_bao"] = hau_kiem["chi_tiet_canh_bao"]
    if loi_dinh_dang:
        ket_qua_cham["canh_bao_loi_dinh_dang"] = (
            f"Các tiêu chí bị judge trả sai định dạng (đã mặc định fail): {', '.join(loi_dinh_dang)}. "
            f"raw_response đã lưu riêng để soát tay."
        )
        ket_qua_cham["raw_response_loi"] = raw
    if tong_thieu > 0:
        ket_qua_cham["canh_bao_thieu_nguon"] = (
            f"{tong_thieu}/{tong_bai} bài không khớp được với văn bản nguồn "
            f"(chỉ còn tiêu đề) - kết quả chấm có thể KHÔNG ĐÁNG TIN CẬY."
        )
    return ket_qua_cham


def _thong_ke_moi() -> dict:
    return {"dat": 0, "khong_dat": 0, "bo_qua": 0, "fail_theo_tieu_chi": Counter()}


def _cap_nhat_thong_ke(tk: dict, cham: dict) -> None:
    v = cham.get("verdict_cuoi")
    if v == "DAT":
        tk["dat"] += 1
    elif v == "KHONG_DAT":
        tk["khong_dat"] += 1
    else:
        tk["bo_qua"] += 1
    for tc, kq in (cham.get("tieu_chi") or {}).items():
        if isinstance(kq, dict) and kq.get("verdict") == "fail":
            tk["fail_theo_tieu_chi"][tc] += 1


def _in_tong_ket(tk: dict, thoi_gian_giay: float, so_cham_moi: int, so_dung_lai: int) -> None:
    tong = tk["dat"] + tk["khong_dat"] + tk["bo_qua"]
    print("\n" + "=" * 55)
    print(f"ĐÃ CHẤM XONG {so_cham_moi} persona mới (dùng lại kết quả cũ: {so_dung_lai})")
    print(f"Thời gian: {thoi_gian_giay:.1f}s ({thoi_gian_giay / 60:.1f} phút)")
    print(f"PASS (đạt cả {len(TIEU_CHI)} tiêu chí):       {tk['dat']}/{tong}")
    print(f"FAIL (trượt ít nhất 1 tiêu chí): {tk['khong_dat']}/{tong}")
    if tk["bo_qua"]:
        print(f"Bỏ qua/lỗi (rỗng, lỗi parse, không có persona): {tk['bo_qua']}/{tong}")
    if tk["khong_dat"]:
        print("Số persona fail theo từng tiêu chí:")
        for tc in TIEU_CHI:
            print(f"  - {tc}: {tk['fail_theo_tieu_chi'].get(tc, 0)}")
    print("=" * 55)


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
        t0 = time.time()
        cham = cham_1_persona(persona, ket_qua_rss, index_theo_link, index_theo_title, client)
        out_path = EVAL_DIR / f"{args.id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cham, f, ensure_ascii=False, indent=2)
        print(f"[{args.id}] xong -> {out_path}")
        if cham.get("can_soat_tay"):
            print(f"  ⚠ có {len(cham['hau_kiem_canh_bao'])} cảnh báo hậu kiểm - cần soát tay:")
            for cb in cham["hau_kiem_canh_bao"]:
                print(f"      - {cb}")

        tk = _thong_ke_moi()
        _cap_nhat_thong_ke(tk, cham)
        _in_tong_ket(tk, time.time() - t0, so_cham_moi=1, so_dung_lai=0)
    else:
        danh_sach_file = sorted(JSON_DIR.glob("*.json"))
        if args.so_luong:
            danh_sach_file = danh_sach_file[:args.so_luong]

        print("Tổng số kết quả cần chấm:", len(danh_sach_file))
        t_bat_dau = time.time()
        tk = _thong_ke_moi()
        so_cham_moi = 0
        so_dung_lai = 0

        for json_path in danh_sach_file:
            persona_id = json_path.stem
            out_path = EVAL_DIR / f"{persona_id}.json"
            if out_path.exists():
                # van tinh vao thong ke de tong ket phan anh du bo du lieu
                with open(out_path, encoding="utf-8") as f:
                    _cap_nhat_thong_ke(tk, json.load(f))
                so_dung_lai += 1
                print(f"[{persona_id}] đã chấm rồi, bỏ qua (vẫn tính vào thống kê).")
                continue

            persona = persona_index.get(persona_id)
            if persona is None:
                tk["bo_qua"] += 1
                print(f"[{persona_id}] không tìm thấy persona tương ứng, bỏ qua.")
                continue

            with open(json_path, encoding="utf-8") as f:
                ket_qua_rss = json.load(f)

            print(f"[{persona_id}] đang chấm...")
            t0 = time.time()
            cham = cham_1_persona(persona, ket_qua_rss, index_theo_link, index_theo_title, client)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(cham, f, ensure_ascii=False, indent=2)
            so_cham_moi += 1
            _cap_nhat_thong_ke(tk, cham)

            print(
                f"[{persona_id}] xong: {cham.get('verdict_cuoi', 'BỎ QUA')} "
                f"({cham.get('so_tieu_chi_dat', 0)}/{len(TIEU_CHI)} tiêu chí), {time.time() - t0:.1f}s"
            )
            if cham.get("can_soat_tay"):
                print(f"  ⚠ [{persona_id}] có {len(cham['hau_kiem_canh_bao'])} cảnh báo hậu kiểm - cần soát tay:")
                for cb in cham["hau_kiem_canh_bao"]:
                    print(f"      - {cb}")

        _in_tong_ket(tk, time.time() - t_bat_dau, so_cham_moi, so_dung_lai)