import re
import json
import os
import hashlib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[3]

MD_ROOT = ROOT_DIR / "multi_document_variants"
SHARED_ROOT = ROOT_DIR / "shared"

DATA_DIR = MD_ROOT / "data"
OUTPUT_DIR = MD_ROOT / "output" / "bao_chi" / "rss_summary"

from pipeline.utils import retry_generate, SUMMARY_MODEL_NAME, load_graph
from pipeline.profiles.ontology_context_state import lay_ontology_context_cho_nganh

_ONTOLOGY_PATH = MD_ROOT / "persona_states.ttl"
_STATE_GRAPH = load_graph(str(_ONTOLOGY_PATH))

_GENRES_PATH = SHARED_ROOT / "config" / "article_genres.json"

with open(_GENRES_PATH, encoding="utf-8") as f:
    _GENRE_DATA = json.load(f)

GENRE_KEYWORDS = _GENRE_DATA["genres"]
GENRE_PRIORITY = _GENRE_DATA.get("genre_priority", [])
DEFAULT_GENRE = _GENRE_DATA.get("default_genre", "Thời sự / Xã hội")

_OVERLAP_PATH = SHARED_ROOT / "config" / "genre_overlap.json"

with open(_OVERLAP_PATH, encoding="utf-8") as f:
    _OVERLAP_DATA = json.load(f)

GENRE_OVERLAP = _OVERLAP_DATA.get("overlap", {})
NGUONG_LIEN_QUAN_GIAN_TIEP = _OVERLAP_DATA.get("nguong_lien_quan_gian_tiep", 0.3)

# nguong rieng cho RSS, chi dung title+summary nen it nhieu hon van ban dai
RSS_SCORE_THRESHOLD = 0.6
RSS_PRIORITY_TIE_MARGIN = 0.15

# trong so theo vi tri trong list chu_de (chinh -> phu 1 -> phu 2 -> ...)
CHU_DE_WEIGHTS = [1.0, 0.6, 0.4]
CHU_DE_WEIGHT_FALLBACK = 0.3  # neu chu_de co nhieu hon 3 phan tu

FILTER_DIR = MD_ROOT / "output" / "rss_filter"
FILTER_TOKENS_UOC_LUONG_MOI_BAI = 30
FILTER_MAX_TOKENS_SAN = 2048

# max_output_tokens duoc tinh DONG theo so luong tin thuc te (xem tom_tat_rss_cho_persona).
TOKENS_UOC_LUONG_MOI_BAI = 200  # uoc luong so token can de tom tat 1 tin (CAN HIEU CHINH sau khi test thuc te)
MAX_OUTPUT_TOKENS_SAN = 4096  # san toi thieu, du cho persona it tin
MAX_OUTPUT_TOKENS_TRAN = 65536  # tran an toan - PHAI kiem tra dung bang gioi han that cua model dang dung, xem muc "Cần xác nhận" ben duoi

TI_LE_BAO_PHU_TOI_THIEU = 0.85  # ti le toi thieu (so doan thuc te / so_bai) chap nhan duoc, duoi muc nay coi la model tu y bo/gop tin

OPENING_STYLES_MO_BAI = [
    "Mở bằng một câu nêu bao quát các nhóm vấn đề/xu hướng nổi bật sẽ xuất hiện trong bài, KHÔNG nêu tên sự kiện cụ thể, KHÔNG nêu số liệu, KHÔNG nhắc đến bất kỳ tin riêng lẻ nào.",
    "Mở bằng cách nêu mối liên hệ giữa các nhóm chủ đề sắp trình bày với định hướng công việc trước mắt của người đọc, giữ ở mức khái quát, KHÔNG đi vào nội dung của tin cụ thể nào.",
    "Mở bằng một nhận định ngắn gọn về bối cảnh chung bao trùm các nhóm tin sắp tóm tắt, KHÔNG nêu tên bất kỳ sự kiện hay tin cụ thể nào.",
    "Mở bằng cách nêu khái quát (không liệt kê tên tin) các mảng nội dung chính sẽ được đề cập, theo đúng thứ tự ưu tiên nhóm chủ đề, KHÔNG đi vào chi tiết của tin nào.",
]
CLOSING_STYLES = [
    "Kết bằng một câu chốt nêu điểm cần lưu ý gần nhất, đặt NGAY SAU phần tóm tắt các ý chính, không dùng cụm 'nhìn chung' hay 'kết lại'.",
    "Kết bằng cách quay lại liên hệ với tin đầu tiên sau khi đã tóm tắt các ý chính, không liệt kê lại nguyên văn các ý đã nêu.",
    "Kết bằng cách nêu điểm cần theo dõi tiếp theo, đặt NGAY SAU phần tóm tắt các ý chính — câu này KHÔNG được thay thế phần tóm tắt.",
    "Kết bằng một câu nhấn mạnh mức độ ưu tiên của ý quan trọng nhất vừa tóm tắt, không lặp nguyên văn câu đã viết ở thân bài.",
]


def nhom_tin_theo_chu_de(persona: dict, ranked_articles: list) -> list:
    """
    Nhom bai da xep hang theo tung chu_de cua persona, giu dung thu tu uu
    tien (chu_de chinh truoc, phu sau). Chi tra ve nhom co it nhat 1 bai.
    """
    chu_de_list = persona.get("chu_de", [])
    nhom = []
    for i, cd in enumerate(chu_de_list):
        bai = [a for a in ranked_articles if a.get("genre") == cd]
        if bai:
            nhom.append({"chu_de": cd, "trong_so": _weight_of_chu_de(i), "bai": bai})
    return nhom


def tim_tin_lien_quan_gian_tiep(persona: dict, articles: list, da_chon: list) -> list:
    chu_de_list = persona.get("chu_de", [])
    if not chu_de_list:
        return []

    da_chon_id = {id(a) for a in da_chon}
    ung_vien = []
    for a in articles:
        if id(a) in da_chon_id:
            continue
        genre = a.get("genre")
        if genre in chu_de_list:
            continue  # da thuoc chu_de chinh, khong phai gian tiep
        diem_overlap = 0.0
        for cd in chu_de_list:
            diem_overlap = max(diem_overlap, GENRE_OVERLAP.get(cd, {}).get(genre, 0.0))
        if diem_overlap >= NGUONG_LIEN_QUAN_GIAN_TIEP:
            ung_vien.append((diem_overlap, a))

    ung_vien.sort(
        key=lambda x: (x[0], x[1].get("genre_score", 0.0)),
        reverse=True
    )

    # Số tin gián tiếp tối đa = 1/3 số tin chính, tối thiểu 3, tối đa 10 (chưa tính tin bị hạ ở bước lọc)
    max_tin_gian_tiep = min(
        10,  # tối đa 10 tin
        max(3, len(da_chon) // 3)
    )

    return [a for _, a in ung_vien[:max_tin_gian_tiep]]


CHUC_VU_LANH_DAO_KEYWORDS = [
    "giám đốc", "trưởng phòng", "trưởng nhóm", "cục trưởng",
    "vụ trưởng", "chủ tịch", "phó chủ tịch", "bí thư", "trưởng", "lãnh đạo",
]

GENRE_LUON_DAY_DU = {"Chính trị / Pháp luật", "Quốc phòng / An ninh"}

OPENING_STYLES = [
    "Mở thẳng bằng số liệu hoặc sự kiện cụ thể nhất trong tin xếp hạng cao nhất, không dẫn dắt, không nêu bối cảnh chung.",
    "Mở bằng cách liên hệ trực tiếp tới mối quan tâm trước mắt hoặc nhiệm vụ hiện tại của người đọc, rồi mới dẫn vào tin liên quan.",
    "Mở bằng một nhận định hoặc câu hỏi ngắn liên quan trực tiếp đến công việc của người đọc, sau đó lập tức nối vào tin số 1.",
    "Mở bằng cách tóm tắt nhanh diễn biến chính của tin số 1 dưới dạng một câu khẳng định, không dùng từ 'bối cảnh' hay 'trong bối cảnh'.",
]
# Dung cho persona KHONG can van phong day du (khong co doan ket luan rieng)
CLOSING_STYLES_KHONG_DAY_DU = [
    "Kết bằng một câu chốt ngắn nêu điểm cần lưu ý gần nhất, đặt sau khi đã tóm tắt đủ tất cả các tin, không tổng kết lại toàn bài, không dùng cụm 'nhìn chung' hay 'kết lại'.",
    "Kết bằng cách quay lại liên hệ với tin đầu tiên, đặt sau khi đã tóm tắt đủ tất cả các tin, không liệt kê lại các ý đã nêu.",
    "Kết đột ngột ở tin cuối cùng được đề cập, không thêm đoạn tổng kết riêng.",
    "Kết bằng một điểm cần theo dõi tiếp, ngắn gọn, đặt sau khi đã tóm tắt đủ tất cả các tin, không điểm lại nội dung.",
]

BANNED_PHRASES = [
    "Trong bối cảnh", "Nhìn chung", "Kết lại", "Có thể thấy rằng",
    "Đáng chú ý là", "Trong khi đó", "Bên cạnh đó", "Đối với",
]


def _chon_style(persona_id: str, styles: list) -> str:
    h = int(hashlib.md5(persona_id.encode()).hexdigest(), 16)
    return styles[h % len(styles)]


def _compute_scores(text: str, keyword_map: dict) -> dict:
    text_lower = text.lower()
    scores = {label: 0.0 for label in keyword_map}
    for label, kw_weights in keyword_map.items():
        for kw, w in kw_weights.items():
            if kw in text_lower:
                scores[label] += w
    return scores


def _apply_priority(candidates: set, scores: dict, rules: list) -> set:
    result = set(candidates)
    for rule in rules:
        prefer, over = rule["prefer"], rule["over"]
        if prefer in result and over in result:
            if abs(scores.get(prefer, 0.0) - scores.get(over, 0.0)) <= RSS_PRIORITY_TIE_MARGIN:
                result.discard(over)
    return result


def classify_genre_rss(text: str) -> tuple:
    """
    Phan loai genre rieng cho bai RSS (title+summary), tra ve ca label va diem so
    de dung tie-break khi xep hang. Copy logic tu content_classifier.py nhung
    tach biet hoan toan, khong import chung, de khong lam anh huong pipeline chinh.
    """
    scores = _compute_scores(text, GENRE_KEYWORDS)
    candidates = {label for label, s in scores.items() if s >= RSS_SCORE_THRESHOLD}
    candidates = _apply_priority(candidates, scores, GENRE_PRIORITY)

    if not candidates:
        return DEFAULT_GENRE, 0.0

    best = max(candidates, key=lambda label: scores[label])
    return best, scores[best]


def gan_genre_cho_bai(articles: list) -> list:
    """Phan loai genre cho tung bai RSS, chi lam 1 lan (dung title+summary)."""
    for a in articles:
        text = f"{a.get('title', '')} {a.get('summary', '')}"
        genre, score = classify_genre_rss(text)
        a["genre"] = genre
        a["genre_score"] = score
    return articles


def _weight_of_chu_de(index: int) -> float:
    if index < len(CHU_DE_WEIGHTS):
        return CHU_DE_WEIGHTS[index]
    return CHU_DE_WEIGHT_FALLBACK


def xep_hang_bai_cho_persona(persona: dict, articles: list) -> list:
    chu_de_list = persona.get("chu_de", [])
    if not chu_de_list:
        return []

    theo_chu_de = {cd: [] for cd in chu_de_list}
    for a in articles:
        if a.get("genre") in theo_chu_de and a.get("genre_score", 0.0) > 0.0:
            theo_chu_de[a["genre"]].append(a)
    for cd in theo_chu_de:
        theo_chu_de[cd].sort(key=lambda a: a.get("genre_score", 0.0), reverse=True)

    da_chon = []
    for cd in chu_de_list:
        da_chon.extend(theo_chu_de[cd])

    return da_chon


def lay_chuc_vu(kinh_nghiem_text: str) -> str:
    match = re.search(r"đảm nhiệm vị trí (.+?)\.", kinh_nghiem_text or "")
    return match.group(1).strip() if match else ""


DO_TUOI_NGUONG_TRANG_TRONG = 55


def can_van_phong_day_du(persona: dict, ranked_articles: list) -> bool:
    chuc_vu = lay_chuc_vu(persona.get("kinh_nghiem", "")).lower()
    if any(kw in chuc_vu for kw in CHUC_VU_LANH_DAO_KEYWORDS):
        return True
    if any(a.get("genre") in GENRE_LUON_DAY_DU for a in ranked_articles):
        return True
    if persona.get("do_tuoi", 0) >= DO_TUOI_NGUONG_TRANG_TRONG:
        return True
    return False


def _dinh_dang_danh_sach_tin(articles: list, dung_full_content: bool = True) -> str:
    ds = ""
    for i, a in enumerate(articles, 1):
        noi_dung = (a.get("content") or a.get("summary", "")) if dung_full_content else a.get("summary", "")
        ds += (
            f"\n{i}. [{a.get('genre')}] {a.get('title')}\n"
            f"   Nội dung: {noi_dung}\n"
        )
    return ds


MUC_DO_CHI_TIET = [
    "Mỗi tin trong nhóm này viết thành MỘT ĐOẠN VĂN RIÊNG (không gộp 2 tin trở lên vào cùng 1 "
    "đoạn). ĐỘ DÀI đoạn văn KHÔNG cố định — phụ thuộc vào lượng thông tin thực sự có trong "
    "phần 'Nội dung' của tin: tin có nhiều số liệu, diễn biến, phát biểu, bối cảnh thì viết dài "
    "và đầy đủ tương ứng; tin ít nội dung thì viết ngắn, KHÔNG kéo dài giả tạo. Tóm tắt trọn vẹn "
    "TẤT CẢ ý chính và ý phụ quan trọng, có phân tích sâu, dùng thuật ngữ chuyên ngành phù hợp "
    "(tham khảo Ontology Context nếu có) — đây là phần TRỌNG TÂM của bài, mức độ chuyên sâu cao nhất.",
    "Mỗi tin trong nhóm này viết thành MỘT ĐOẠN VĂN RIÊNG (không gộp 2 tin trở lên vào cùng 1 "
    "đoạn). ĐỘ DÀI đoạn văn co giãn theo lượng nội dung thật có trong tin, không ép về một số "
    "câu cố định. Tóm tắt trọn vẹn ý chính của tin (không bỏ sót ý quan trọng), có thể dùng "
    "thuật ngữ ngành nhưng không cần phân tích sâu như nhóm trọng tâm.",
    "Mỗi tin trong nhóm này viết thành MỘT ĐOẠN VĂN RIÊNG (không gộp 2 tin trở lên vào cùng 1 "
    "đoạn). ĐỘ DÀI đoạn văn co giãn theo lượng nội dung thật có trong tin, không ép về một số "
    "câu cố định. Tóm tắt trọn vẹn ý chính, ngôn ngữ phổ thông, không cần thuật ngữ chuyên "
    "ngành, nhưng vẫn phải nêu đủ nội dung cốt lõi (không chỉ nêu tên tin).",
]


def _muc_do_cho_tang(idx: int) -> str:
    return MUC_DO_CHI_TIET[min(idx, len(MUC_DO_CHI_TIET) - 1)]


def build_filter_prompt(persona: dict, articles: list) -> str:
    ds = ""
    for i, a in enumerate(articles, 1):
        ds += f"\n{i}. {a.get('title')}\n   Tóm tắt gốc: {a.get('summary')}\n"
    cau_hoi_kiem_tra = (
        f"Tin này có phục vụ trực tiếp cho công việc, chuyên môn hoặc nhiệm vụ thực tế của "
        f"một người làm trong ngành \"{persona.get('nganh_to')} - {persona.get('nganh_nho')}\" "
        f"hay không? (dựa vào mô tả chung và định hướng công việc trước mắt của người này ở trên)"
    )
    prompt = f"""Bạn đang lọc tin RSS cho một cán bộ có hồ sơ công vụ sau:

       - Ngành/lĩnh vực: {persona.get('nganh_to')} - {persona.get('nganh_nho')}
       - Đơn vị công tác: {persona.get('to_chuc')}
       - Mô tả chung: {persona.get('mo_ta_chung')}
       - Định hướng công việc trước mắt: {persona.get('cau_hoi_truoc_mat')}

       Câu hỏi kiểm tra cho MỖI tin: "{cau_hoi_kiem_tra}"

       - "giu": CHỈ khi tin có ý nghĩa trực tiếp với công việc/chuyên môn của người này — ví dụ
         chính sách, quy định, số liệu, sự kiện, xu hướng thuộc đúng ngành họ đang làm, mà họ cần
         biết để phục vụ công việc.
       - "ha": tin có nhắc đến từ khóa liên quan đến ngành của họ, nhưng chỉ mang tính CHUYỆN CỦA
         MỘT DOANH NGHIỆP, TỔ CHỨC HOẶC CÁ NHÂN CỤ THỂ, không có ý nghĩa chung với công việc của
         người này. Ví dụ: một công ty tư nhân báo lãi/lỗ, cổ phiếu một doanh nghiệp tăng/giảm,
         một câu lạc bộ thể thao gặp khủng hoảng tài chính, tài sản cá nhân của người nổi tiếng
         thay đổi, một dự án cụ thể của một chủ đầu tư mở bán — dù có nhắc từ khóa cùng ngành,
         những tin này không phục vụ công việc chung của người này.
       - "loai": hoàn toàn không liên quan đến lĩnh vực của người này.

       QUY TẮC MẶC ĐỊNH: nếu phân vân giữa "giu" và "ha", LUÔN chọn "ha". "giu" phải là lựa chọn
       có chủ đích, không phải lựa chọn an toàn.

       Danh sách tin:
       {ds}

       Chỉ trả về DUY NHẤT một mảng JSON, không thêm chữ nào khác, không dùng dấu ```. Mỗi phần
       tử có đúng 2 trường:
       [
         {{"stt": 1, "hanh_dong": "giu"}},
         {{"stt": 2, "hanh_dong": "ha"}}
       ]

       Phải trả đủ {len(articles)} phần tử, đúng theo số thứ tự đã đánh ở trên, không được bỏ sót.
       """.strip()

    return prompt


def loc_bai_lien_quan_persona(persona: dict, ranked_articles: list, client,
                              model_name: str = SUMMARY_MODEL_NAME) -> tuple:
    """
    Goi LLM 1 lan de loc lai danh sach bai da xep theo tu khoa.
    Tra ve tuple (bai_giu, bai_ha). bai_ha se duoc gop chung voi nhom
    "tin lien quan gian tiep" o buoc tom tat cuoi. Bai bi danh dau "loai"
    thi khong xuat hien o ca 2 danh sach nay.
    """
    if not ranked_articles:
        return [], []

    prompt = build_filter_prompt(persona, ranked_articles)
    max_tokens = MAX_OUTPUT_TOKENS_TRAN

    def _call():
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.0,
                "max_output_tokens": max_tokens,
            },
        )

    response = retry_generate(_call)
    text = response.text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    matches = re.findall(
        r'\{\s*"stt"\s*:\s*(\d+)\s*,\s*"hanh_dong"\s*:\s*"(\w+)"\s*\}',
        text,
    )
    hanh_dong_theo_stt = {int(stt): hanh_dong for stt, hanh_dong in matches}

    if not hanh_dong_theo_stt:
        print(f"[loc_bai_lien_quan_persona] KHONG LAY DUOC OBJECT NAO TU RESPONSE, giu nguyen tat ca.")
        print(f"[loc_bai_lien_quan_persona] RAW RESPONSE (500 ky tu dau):\n{text[:500]}")
        return ranked_articles, []

    if len(hanh_dong_theo_stt) < len(ranked_articles):
        print(
            f"[loc_bai_lien_quan_persona] CANH BAO: chi lay duoc "
            f"{len(hanh_dong_theo_stt)}/{len(ranked_articles)} tin (co the do bi cat cut), "
            f"cac tin con lai mac dinh giu."
        )

    bai_giu = []
    bai_ha = []
    for i, a in enumerate(ranked_articles, 1):
        hanh_dong = hanh_dong_theo_stt.get(i, "giu")  # thieu thi mac dinh giu, tranh mat tin oan
        if hanh_dong == "giu":
            bai_giu.append(a)
        elif hanh_dong == "ha":
            bai_ha.append(a)
        # hanh_dong == "loai" thi khong dua vao dau ca

    return bai_giu, bai_ha


def loc_bai_lien_quan_persona_co_cache(persona: dict, ranked_articles: list, client,
                                       model_name: str = SUMMARY_MODEL_NAME) -> tuple:
    """
    Giong loc_bai_lien_quan_persona nhung co luu cache ra file trong
    FILTER_DIR, de khong phai goi lai LLM moi lan chay lai script.
    """
    FILTER_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = FILTER_DIR / f"{persona.get('id')}.json"

    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        bai_theo_link = {a.get("link"): a for a in ranked_articles}
        bai_giu = [bai_theo_link[link] for link in cache["giu"] if link in bai_theo_link]
        bai_ha = [bai_theo_link[link] for link in cache["ha"] if link in bai_theo_link]
        return bai_giu, bai_ha

    bai_giu, bai_ha = loc_bai_lien_quan_persona(persona, ranked_articles, client, model_name)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "giu": [a.get("link") for a in bai_giu],
                "ha": [a.get("link") for a in bai_ha],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return bai_giu, bai_ha


def build_rss_prompt(persona: dict, ranked_articles: list, tin_gian_tiep: list = None) -> str:
    day_du = can_van_phong_day_du(persona, ranked_articles)
    ontology_ctx = lay_ontology_context_cho_nganh(persona.get("nganh_to", ""))
    nhom_tin = nhom_tin_theo_chu_de(persona, ranked_articles)
    tin_gian_tiep = tin_gian_tiep or []

    opening_style = (
        _chon_style(persona.get("id", ""), OPENING_STYLES_MO_BAI)
        if day_du
        else _chon_style(persona.get("id", ""), OPENING_STYLES)
    )
    closing_style = _chon_style(
        persona.get("id", "") + "_close",
        CLOSING_STYLES if day_du else CLOSING_STYLES_KHONG_DAY_DU,
    )

    if day_du:
        yeu_cau_van_phong = (
            "Bài viết PHẢI bắt đầu bằng một dòng TIÊU ĐỀ in đậm, viết hoa hoặc in đậm, "
            "ngắn gọn, nêu khái quát chủ đề bản tin — đây là dòng đầu tiên của toàn văn bản, "
            "đứng TRƯỚC phần thân bài. Sau tiêu đề mới đến thân bài viết theo bố cục đầy đủ, "
            "chuyên nghiệp, gồm mở bài, thân bài và kết luận."
        )
    else:
        yeu_cau_van_phong = (
            "Bài viết KHÔNG có tiêu đề — viết thẳng vào nội dung ngay từ câu/dòng đầu tiên, "
            "ngắn gọn, dễ đọc."
        )

    if day_du:
        yeu_cau_bo_cuc = f"""
        - BỐ CỤC BẮT BUỘC gồm 3 phần rõ ràng, cách nhau bằng dấu xuống dòng:
        1. ĐOẠN MỞ BÀI (ngay sau tiêu đề, TÁCH RIÊNG thành một đoạn độc lập, không phải đoạn
           tóm tắt của tin nào): 2-3 câu nêu khái quát những nhóm chủ đề nổi bật sẽ được đề cập
           trong bài, không đi vào chi tiết số liệu cụ thể của từng tin. Phong cách viết câu
           đầu tiên: {opening_style}
           BẮT BUỘC: đoạn này phải kết thúc và XUỐNG DÒNG TRỐNG trước khi đoạn tóm tắt tin đầu
           tiên (thuộc THÂN BÀI) bắt đầu — hai đoạn này không được viết dính liền hoặc lồng
           vào nhau dưới bất kỳ hình thức nào.
           LƯU Ý QUAN TRỌNG: dù đoạn mở bài có nhắc tới tin xếp hạng cao nhất, tin đó VẪN PHẢI
           có một đoạn văn RIÊNG, đầy đủ trong phần THÂN BÀI như mọi tin khác cùng nhóm chủ đề
           — đoạn mở bài chỉ là câu dẫn ngắn, KHÔNG được thay thế cho đoạn tóm tắt đầy đủ của
           tin đó.
        2. THÂN BÀI: các đoạn tóm tắt từng tin theo đúng nhóm chủ đề (xem chi tiết bên dưới).
           Khi CHUYỂN từ nhóm chủ đề này sang nhóm chủ đề khác, đoạn đầu tiên của nhóm mới
           PHẢI mở đầu bằng một câu dẫn ngắn (không quá 1 câu) báo hiệu đang chuyển sang chủ
           đề mới, nêu tên nhóm chủ đề đó một cách tự nhiên trong câu văn — câu dẫn này nằm
           chung trong đoạn tóm tắt tin đầu tiên của nhóm, KHÔNG tính là một đoạn riêng.
           QUAN TRỌNG: NHÓM CHỦ ĐỀ ĐẦU TIÊN ("{nhom_tin[0]['chu_de'] if nhom_tin else ''}")
           KHÔNG được có câu dẫn kiểu "Chuyển sang nhóm..." — nhóm này đã được đoạn mở bài
           giới thiệu ngầm rồi, tin đầu tiên của bài viết thẳng vào nội dung. Câu dẫn CHỈ áp
           dụng khi thực sự đổi từ nhóm chủ đề A sang nhóm chủ đề B khác — giữa các tin CÙNG
           một nhóm (ví dụ tin thứ 2, thứ 3 trong cùng nhóm đầu tiên) TUYỆT ĐỐI KHÔNG được lặp
           lại câu dẫn "Chuyển sang nhóm..." của nhóm đó.
           Thứ tự các nhóm chủ đề theo đúng trình tự sau: {" -> ".join(n["chu_de"] for n in nhom_tin)}.
           Số câu dẫn chuyển nhóm BẮT BUỘC phải có, chính xác bằng {max(0, len(nhom_tin) - 1)}
           (bằng số nhóm trừ 1, vì nhóm đầu tiên không cần câu dẫn) — không nhiều hơn, không
           ít hơn.
           Ví dụ ĐÚNG (1 đoạn): "Chuyển sang nhóm Thời sự - Xã hội, Bộ Nội vụ đề xuất bỏ
           thời hạn tối đa 12 tháng đối với văn bản ủy quyền nhận lương hưu..."
           Ví dụ SAI: để câu "Chuyển sang nhóm Thời sự - Xã hội..." đứng một mình thành
           một đoạn, rồi mới xuống dòng sang đoạn tóm tắt tin.
           Ví dụ SAI khác: viết "Chuyển sang nhóm Tài chính - Kế toán" ở tin thứ 2 trong khi
           tin thứ 1 cũng đã thuộc nhóm Tài chính - Kế toán (không có chuyển nhóm thật).
        3. ĐOẠN KẾT LUẬN (TÁCH RIÊNG thành một đoạn độc lập, đứng sau tất cả các nhóm chủ đề
           và tin gián tiếp, không phải đoạn tóm tắt của tin nào): 2-4 câu tổng kết lại 2-3
           điểm quan trọng nhất trong toàn bài theo đúng thứ tự ưu tiên, diễn đạt lại ngắn gọn
           hơn (không lặp nguyên văn câu đã viết ở thân bài). Phong cách viết câu cuối cùng:
           {closing_style}"""
    else:
        # nhanh nay truoc day KHONG co yeu cau cau dan chuyen nhom, trong khi judge
        # (bo_cuc_uu_tien) lai kiem tra cau dan -> luon fail voi persona nhieu nhom.
        chuyen_nhom = ""
        if len(nhom_tin) >= 2:
            chuyen_nhom = (
                f" CHUYỂN NHÓM CHỦ ĐỀ: thứ tự các nhóm chính là "
                f"{' -> '.join(n['chu_de'] for n in nhom_tin)}. Khi chuyển từ nhóm này sang nhóm "
                f"kế tiếp, đoạn tin ĐẦU TIÊN của nhóm mới PHẢI mở đầu bằng một câu dẫn ngắn (không "
                f"quá 1 câu) nêu tên nhóm chủ đề mới một cách tự nhiên (ví dụ: \"Chuyển sang nhóm "
                f"...,\"), viết dính liền trong đoạn đó — KHÔNG tách thành đoạn riêng, KHÔNG tính là "
                f"một tin. Nhóm đầu tiên KHÔNG có câu dẫn; các tin cùng một nhóm KHÔNG lặp lại câu "
                f"dẫn. Số câu dẫn bắt buộc đúng bằng {len(nhom_tin) - 1}."
            )
        yeu_cau_bo_cuc = (
            f"- Không cần bố cục mở-thân-kết tách riêng — viết thẳng vào nội dung tin theo "
            f"đúng thứ tự nhóm chủ đề. Câu đầu tiên của toàn bài áp dụng phong cách: "
            f"{opening_style}. Câu cuối cùng của toàn bài áp dụng phong cách: {closing_style}. "
            f"LƯU Ý: nếu câu đầu tiên đã nhắc tới nội dung của tin xếp hạng cao nhất, tin đó VẪN "
            f"PHẢI được tóm tắt đầy đủ ở đoạn riêng của nó theo đúng vị trí trong nhóm chủ đề — "
            f"câu mở đầu không thay thế cho đoạn tóm tắt của tin đó."
            f"{chuyen_nhom}"
        )

    cam_cum_tu = ", ".join(f"'{p}'" for p in BANNED_PHRASES)

    ontology_section = ""
    if ontology_ctx:
        ontology_section = f"""
    PHẦN 1: KHUNG PHÂN TÍCH NGÀNH CÔNG VỤ (Ontology Context)
    {ontology_ctx}

    """

    khoi_tin_text = ""
    for idx, n in enumerate(nhom_tin):
        khuynh_huong = ""
        if idx == 0:
            khuynh_huong = (
                f"\n- KHUYNH HƯỚNG PHÂN TÍCH BẮT BUỘC cho nhóm này: chủ động chọn góc nhìn, "
                f"số liệu, hệ quả liên quan TRỰC TIẾP tới định hướng công việc sau đây, để nó "
                f"DẪN DẮT cách bạn diễn giải các tin trong nhóm: "
                f"\"{persona.get('cau_hoi_truoc_mat', '')}\""
            )
        khoi_tin_text += f"""
    NHÓM CHỦ ĐỀ "{n['chu_de']}" (ưu tiên thứ {idx + 1}, gồm {len(n['bai'])} tin):
    {_dinh_dang_danh_sach_tin(n['bai'])}
    Yêu cầu: {_muc_do_cho_tang(idx)}{khuynh_huong}
    """

    khoi_gian_tiep_text = ""
    if tin_gian_tiep:
        khoi_gian_tiep_text = f"""
            NHÓM TIN LIÊN QUAN GIÁN TIẾP (ngoài chủ đề chính của người này, nhưng có liên hệ nhẹ,
            gồm {len(tin_gian_tiep)} tin):
            {_dinh_dang_danh_sach_tin(tin_gian_tiep, dung_full_content=False)}
            Yêu cầu:
        - Đây KHÔNG phải phần trọng tâm của bài — CHỈ giữ lại những tin có giá trị tham khảo
          thực sự rõ ràng đối với công việc của người này; MẠNH DẠN bỏ hẳn những tin chỉ liên
          quan lỏng lẻo hoặc không mang lại giá trị tham khảo cụ thể, kể cả khi phải bỏ nguyên
          một nhóm chủ đề trong danh sách trên.
        - Tổng độ dài của TOÀN BỘ nhóm này không vượt quá 1-2 đoạn văn ngắn cho cả bài — ưu
          tiên SÚC TÍCH hơn là cố gắng nhắc đến nhiều nhóm chủ đề.
        - MỖI đoạn trong nhóm này đều PHẢI bắt đầu bằng một cụm từ ngắn báo hiệu đây là tin
          ngoài chuyên môn chính, ví dụ "Các tin khác đáng chú ý:", "Về [chủ đề X]:".
        - Trong mỗi đoạn, mỗi tin chỉ giữ đúng ý quan trọng nhất (khoảng 1 câu/tin), không mô
          tả chi tiết.
        - Nếu nhiều tin nói về cùng một sự kiện hoặc cùng một chủ đề thì gộp thành một câu.
            """

    prompt = f"""{ontology_section}Bạn đang viết một VĂN BẢN TÓM TẮT TIN TỨC CÁ NHÂN HÓA hàng ngày cho một người có hồ sơ sau:

        - Ngành/lĩnh vực: {persona.get('nganh_to')} - {persona.get('nganh_nho')}
        - Đơn vị công tác: {persona.get('to_chuc')}
        - Mô tả chung: {persona.get('mo_ta_chung')}

    {khoi_tin_text}
    {khoi_gian_tiep_text}

    Yêu cầu bắt buộc chung cho toàn bài: 
    - {yeu_cau_bo_cuc}

    - {yeu_cau_van_phong}

    - CẤU TRÚC BẮT BUỘC: MỖI TIN được viết thành MỘT ĐOẠN VĂN RIÊNG BIỆT, xuống dòng giữa các
      đoạn (mỗi đoạn tương ứng đúng 1 tin trong danh sách trên). KHÔNG gộp 2 tin trở lên vào
      cùng 1 đoạn. Các đoạn cách nhau bằng đúng MỘT DÒNG TRỐNG (tức xuống dòng 2 lần); KHÔNG
      xuống dòng đơn giữa các đoạn và KHÔNG xuống dòng ở giữa một đoạn. KHÔNG đặt tiêu đề kiểu
      "Tin 1:", KHÔNG gạch đầu dòng — đoạn văn tự nhiên. NGOẠI LỆ DUY NHẤT: câu
      dẫn chuyển nhóm chủ đề (xem mục BỐ CỤC) viết dính liền đầu đoạn tin đầu tiên của nhóm
      mới, không xuống dòng riêng, không tính là một đoạn/tin.

    - KHÔNG viết các đoạn tin theo cùng một khuôn mẫu số câu hay cấu trúc câu lặp lại (ví dụ:
      luôn đúng 2 câu, luôn theo mẫu "câu 1 nêu sự kiện — câu 2 nêu hệ quả/lo ngại"). Mỗi đoạn
      cần có độ dài và cách triển khai câu khác nhau, phản ánh đúng lượng và tính chất thông
      tin của tin đó — có tin chỉ cần 1 câu, có tin cần 4-5 câu nếu nội dung phong phú.

    - Trong CÙNG một nhóm chủ đề, các đoạn tin không bắt buộc phải liền mạch với nhau như
      một bài luận — ưu tiên tóm tắt đầy đủ, rõ ràng từng tin hơn là ưu tiên chuyển ý mượt
      giữa các tin trong cùng nhóm. Câu dẫn chuyển ý CHỈ bắt buộc khi chuyển sang nhóm chủ đề
      mới (xem yêu cầu bố cục ở trên).

    - TUYỆT ĐỐI KHÔNG dùng các cụm sau ở bất kỳ đâu trong bài: {cam_cum_tu}.

    - Không dùng quá 2 lần bất kỳ cụm chuyển đoạn nào trong toàn bài.

    - Đề cập nhóm ưu tiên cao trước, mức độ chi tiết giảm dần đúng theo thứ tự nhóm ở trên
      (mức độ chi tiết ở đây là ĐỘ SÂU/ĐỘ DÀI của từng đoạn — KHÔNG được gộp nhiều tin lại
      thành ít đoạn hơn ở bất kỳ nhóm chủ đề chính nào, kể cả nhóm ưu tiên thấp nhất); nhóm
      tin liên quan gián tiếp (nếu có) luôn đặt ở cuối bài, sau tất cả nhóm chủ đề chính.

    - Đối với các tin thuộc NHÓM CHỦ ĐỀ CHÍNH (đã được lọc sẵn là có liên quan): KHÔNG được bỏ
      tin nào, KHÔNG được gộp tin nào — mỗi tin đúng 1 đoạn riêng. Chỉ điều chỉnh ĐỘ DÀI/ĐỘ SÂU
      theo tính chất tin:
        - Tin ảnh hưởng tới chính sách, pháp luật, kinh tế vĩ mô, ngân sách, quản lý nhà nước
        hoặc công việc hiện tại:
            -> tóm tắt đầy đủ, chi tiết.
        - Tin doanh nghiệp, thị trường, đời sống, giải trí hoặc cá nhân, chỉ có ý nghĩa tham khảo:
            -> viết ngắn hơn nhưng vẫn nêu đủ ý cốt lõi và vẫn có đoạn riêng.

    - Quyền lược bỏ hoặc gộp CHỈ áp dụng cho NHÓM TIN LIÊN QUAN GIÁN TIẾP (xem yêu cầu của nhóm
      đó ở trên). Tin nhóm chủ đề chính PHẢI tóm tắt đầy đủ ý chính (xem yêu cầu độ chi tiết
      riêng từng nhóm ở trên); tin gián tiếp tóm sơ ý chính nhất nhưng vẫn phải có nội dung,
      không được chỉ nêu tên tin suông.

    - Không tự suy luận, đánh giá hoặc rút ra bài học nếu bài báo không nêu. Không thêm các nhận định như:
        - cho thấy
        - phản ánh
        - là lời cảnh báo
        - minh chứng
        - bài học
        - gợi mở
    trừ khi ý đó xuất hiện rõ trong bài gốc.

    - Chỉ trả về nội dung văn bản, không thêm lời dẫn kiểu "Dưới đây là...".
    """.strip()

    return prompt


NGUONG_TRUNG_BIGRAM_BO_SOT = 0.3  # duoi muc nay coi la nghi ngo bo sot (heuristic, CAN HIEU CHINH)


def _bigram_am_tiet(text: str) -> set:
    tokens = re.findall(r"\w+", (text or "").lower())
    return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}


def kiem_tra_bai_bi_bo_sot(ranked_articles: list, summary: str) -> list:
    """
    Heuristic: summary paraphrase nen KHONG the doi title khop nguyen 4 tu dau.
    Thay vao do so ti le cap am tiet lien tiep (bigram) cua title xuat hien trong
    summary; duoi NGUONG_TRUNG_BIGRAM_BO_SOT thi nghi ngo bai bi bo sot.
    Tra ve danh sach title nghi ngo.
    """
    bigram_summary = _bigram_am_tiet(summary)
    bai_nghi_ngo_thieu = []
    for a in ranked_articles:
        title = a.get("title", "")
        bigram_title = _bigram_am_tiet(title)
        if not bigram_title:
            continue
        ti_le = len(bigram_title & bigram_summary) / len(bigram_title)
        if ti_le < NGUONG_TRUNG_BIGRAM_BO_SOT:
            bai_nghi_ngo_thieu.append(title)
    return bai_nghi_ngo_thieu


def tom_tat_rss_cho_persona(persona: dict, articles: list, client,
                            model_name: str = SUMMARY_MODEL_NAME) -> dict:
    ranked_truoc_loc = xep_hang_bai_cho_persona(persona, articles)

    if not ranked_truoc_loc:
        return {
            "id": persona.get("id"),
            "summary": "",
            "ranked_articles": [],
            "note": "Không có tin nào khớp chu_de của persona này.",
        }

    ranked, bai_bi_ha = loc_bai_lien_quan_persona_co_cache(persona, ranked_truoc_loc, client)

    if not ranked and not bai_bi_ha:
        return {
            "id": persona.get("id"),
            "summary": "",
            "ranked_articles": [],
            "note": "Tất cả tin khớp chu_de đều bị lọc bỏ vì không thực sự hữu ích cho persona này.",
        }

    nhom_tin = nhom_tin_theo_chu_de(persona, ranked)
    tin_gian_tiep = bai_bi_ha + tim_tin_lien_quan_gian_tiep(persona, articles, ranked)

    prompt = build_rss_prompt(persona, ranked, tin_gian_tiep)

    so_bai = len(ranked) + len(tin_gian_tiep)
    max_tokens = min(
        MAX_OUTPUT_TOKENS_TRAN,
        max(MAX_OUTPUT_TOKENS_SAN, so_bai * TOKENS_UOC_LUONG_MOI_BAI),
    )

    def _call():
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.0,
                "max_output_tokens": max_tokens,
            },
        )

    response = retry_generate(_call)

    bi_cat_cut = False
    try:
        finish_reason = str(response.candidates[0].finish_reason)
        if "MAX_TOKENS" in finish_reason:
            bi_cat_cut = True
    except (AttributeError, IndexError):
        pass

    # chuan hoa: moi lan xuong dong (don hay nhieu) -> dung 1 dong trong, de dem doan
    # va de judge tach doan khong bi lech neu model chi xuong dong don.
    summary = re.sub(r"\s*\n\s*", "\n\n", response.text.strip())
    so_doan_thuc_te = len([doan for doan in summary.split("\n\n") if doan.strip()])
    so_tin_chinh = len(ranked)
    ti_le_bao_phu = so_doan_thuc_te / so_tin_chinh if so_tin_chinh else 0.0
    bai_nghi_ngo_thieu = kiem_tra_bai_bi_bo_sot(ranked, summary)
    notes = []
    if not nhom_tin or nhom_tin[0]["chu_de"] != persona.get("chu_de", [""])[0]:
        notes.append(
            f"Không có tin nào khớp đúng chủ đề chuyên môn chính "
            f"(\"{persona.get('chu_de', [''])[0]}\") trong đợt tin này."
        )
    if bi_cat_cut:
        notes.append(
            f"CẢNH BÁO: bản tóm tắt có thể bị CẮT CỤT do chạm giới hạn "
            f"{max_tokens} token (ước lượng từ {so_bai} tin) — cần chạy lại persona này "
            f"riêng với TOKENS_UOC_LUONG_MOI_BAI hoặc MAX_OUTPUT_TOKENS_TRAN cao hơn."
        )
    if so_tin_chinh > 0 and ti_le_bao_phu < TI_LE_BAO_PHU_TOI_THIEU:
        notes.append(
            f"CẢNH BÁO: bài viết chỉ có {so_doan_thuc_te} đoạn, trong khi nhóm tin chính "
            f"(bắt buộc mỗi tin 1 đoạn riêng) có {so_tin_chinh} tin — có khả năng model đã "
            f"tự gộp hoặc bỏ bớt tin chính dù prompt cấm điều này."
        )
    if bai_nghi_ngo_thieu:
        notes.append(
            f"CẢNH BÁO: {len(bai_nghi_ngo_thieu)} bài thuộc nhóm chủ đề chính có thể đã bị bỏ "
            f"sót hoàn toàn (không tìm thấy dấu vết trong bản tóm tắt): "
            + "; ".join(bai_nghi_ngo_thieu)
        )
    ket_qua = {
        "id": persona.get("id"),
        "summary": summary,
        "so_luong_tin_da_dua_vao": so_bai,
        "so_nhom_chu_de": len(nhom_tin),
        "do_dai_prompt_ky_tu": len(prompt),
        "so_doan_thuc_te": so_doan_thuc_te,
        "ti_le_bao_phu": round(ti_le_bao_phu, 2),
        "ranked_articles": [
            {"title": a["title"], "genre": a["genre"], "genre_score": a["genre_score"], "link": a.get("link")}
            for a in ranked
        ],
        "tin_gian_tiep": [
            {"title": a["title"], "genre": a["genre"], "genre_score": a["genre_score"], "link": a.get("link")}
            for a in tin_gian_tiep
        ],
    }
    if notes:
        ket_qua["note"] = " | ".join(notes)

    return ket_qua


if __name__ == "__main__":
    import argparse
    import time
    from google import genai

    API_KEY = os.getenv("API_KEY")

    parser = argparse.ArgumentParser(description="Tom tat RSS ca nhan hoa")

    parser.add_argument(
        "--id",
        type=str,
        help="id cua persona, vi du NN0001"
    )

    parser.add_argument(
        "-n", "--so-luong",
        type=int,
        help="Chi duyet N persona dau tien"
    )

    args = parser.parse_args()

    with open(DATA_DIR / "vnexpress_rss_snapshot.json", encoding="utf-8") as f:
        articles = json.load(f)

    with open(DATA_DIR / "profile" / "state_profiles.json", encoding="utf-8") as f:
        personas = json.load(f)

    articles = gan_genre_cho_bai(articles)

    client = genai.Client(api_key=API_KEY)

    JSON_DIR = OUTPUT_DIR / "json"
    MD_DIR = OUTPUT_DIR / "md"

    JSON_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    # ==========================================================
    # CHẠY 1 PERSONA
    # ==========================================================
    if args.id:
        persona = next((p for p in personas if p.get("id") == args.id), None)
        if persona is None:
            raise SystemExit(f"Không tìm thấy persona có id = {args.id}")
        print(f"[{persona['id']}] bắt đầu xử lý...")
        t0 = time.time()

        ket_qua = tom_tat_rss_cho_persona(persona, articles, client)

        out_path_json = JSON_DIR / f"{persona['id']}.json"
        with open(out_path_json, "w", encoding="utf-8") as f:
            json.dump(ket_qua, f, ensure_ascii=False, indent=2)

        out_path_md = MD_DIR / f"{persona['id']}.md"
        with open(out_path_md, "w", encoding="utf-8") as f:
            f.write(ket_qua["summary"])

        print(f"[{persona['id']}] xong, mất {time.time() - t0:.1f}s")
        print(f"Đã ghi json: {out_path_json}")
        print(f"Đã ghi md:   {out_path_md}")
    else:
        danh_sach_persona = personas
        if args.so_luong:
            danh_sach_persona = danh_sach_persona[:args.so_luong]
        print("Tổng số persona cần duyệt:", len(danh_sach_persona))
        t_bat_dau = time.time()

        for persona in danh_sach_persona:
            persona_id = persona["id"]
            out_path_json = JSON_DIR / f"{persona_id}.json"
            if out_path_json.exists():
                print(f"[{persona_id}] đã có kết quả rồi, bỏ qua.")
                continue
            print(f"[{persona_id}] bắt đầu xử lý...")
            t0 = time.time()

            ket_qua = tom_tat_rss_cho_persona(persona, articles, client)
            with open(out_path_json, "w", encoding="utf-8") as f:
                json.dump(ket_qua, f, ensure_ascii=False, indent=2)

            out_path_md = MD_DIR / f"{persona_id}.md"
            with open(out_path_md, "w", encoding="utf-8") as f:
                f.write(ket_qua["summary"])

            print(f"[{persona_id}] xong, mất {time.time() - t0:.1f}s")
            print("=================================")

        print(
            "\nXONG HẾT. Tổng thời gian:",
            round((time.time() - t_bat_dau) / 60, 1),
            "phút"
        )