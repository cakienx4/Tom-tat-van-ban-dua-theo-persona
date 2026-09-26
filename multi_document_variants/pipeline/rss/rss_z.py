import re
import json
import os
import hashlib
from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]

MD_ROOT = ROOT_DIR / "multi_document_variants"
SHARED_ROOT = ROOT_DIR / "shared"

DATA_DIR = MD_ROOT / "data"
OUTPUT_DIR = MD_ROOT / "output" / "rss_summary"

from multi_document_variants.pipeline.utils import retry_generate, SUMMARY_MODEL_NAME, load_graph
from multi_document_variants.pipeline.rss.ontology_context_state import lay_ontology_context_cho_nganh

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

# max_output_tokens duoc tinh DONG theo so luong tin thuc te (xem tom_tat_rss_cho_persona).
TOKENS_UOC_LUONG_MOI_BAI = 200  # uoc luong so token can de tom tat 1 tin (CAN HIEU CHINH sau khi test thuc te)
MAX_OUTPUT_TOKENS_SAN = 4096  # san toi thieu, du cho persona it tin
MAX_OUTPUT_TOKENS_TRAN = 32768  # tran an toan - PHAI kiem tra dung bang gioi han that cua model dang dung, xem muc "Cần xác nhận" ben duoi

TY_LE_TU_COT_LOI = 0.65  # % độ dài dành cho tin đúng chuyên môn (chu_de chính)
TY_LE_TU_LIEN_QUAN = 0.35  # % còn lại cho tin bối cảnh (chu_de phụ)


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
    """
    Tim TAT CA tin NGOAI chu_de cua persona nhung co overlap gian tiep (theo
    config/genre_overlap.json) voi it nhat 1 chu_de cua persona, vuot
    nguong NGUONG_LIEN_QUAN_GIAN_TIEP. Khong gioi han so luong - lay het,
    xep theo do lien quan (overlap, roi genre_score) giam dan.
    """
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

    # Số tin gián tiếp tối đa = 1/2 số tin chính, nhưng luôn ít nhất 20 tin
    max_tin_gian_tiep = min(
        50,  # tối đa 50 tin
        max(20, len(da_chon) // 2)
    )

    return [a for _, a in ung_vien[:max_tin_gian_tiep]]


CHUC_VU_LANH_DAO_KEYWORDS = [
    "giám đốc", "trưởng phòng", "trưởng nhóm", "cục trưởng",
    "vụ trưởng", "chủ tịch", "phó chủ tịch", "bí thư", "trưởng", "lãnh đạo",
]

GENRE_LUON_DAY_DU = {"Chính trị / Pháp luật", "Quốc phòng / An ninh"}

OPENING_STYLES = [
    "Mở thẳng bằng số liệu hoặc sự kiện cụ thể nhất trong tin xếp hạng cao nhất, không dẫn dắt, không nêu bối cảnh chung. Mở bằng cách liên hệ trực tiếp tới mối quan tâm trước mắt hoặc nhiệm vụ hiện tại của người đọc, rồi mới dẫn vào tin liên quan. Mở bằng một nhận định hoặc câu hỏi ngắn liên quan trực tiếp đến công việc của người đọc, sau đó lập tức nối vào tin số 1. Mở bằng cách tóm tắt nhanh diễn biến chính của tin số 1 dưới dạng một câu khẳng định, không dùng từ 'bối cảnh' hay 'trong bối cảnh'."
]
CLOSING_STYLES = [
    "Kết bằng một câu chốt ngắn nêu điểm cần lưu ý gần nhất, không tổng kết lại toàn bài, không dùng cụm 'nhìn chung' hay 'kết lại'. Kết bằng cách quay lại liên hệ với tin đầu tiên, không liệt kê lại các ý đã nêu. Kết đột ngột ở tin cuối cùng được đề cập, không thêm đoạn tổng kết riêng. Kết bằng một câu hỏi mở hoặc một điểm cần theo dõi tiếp, ngắn gọn, không điểm lại nội dung."
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
    """
    Loc TAT CA bai RSS khop chu_de cua persona (khong gioi han so luong).
    Thu tu: chu_de uu tien cao truoc (theo vi tri trong list chu_de cua
    persona), trong tung chu_de xep theo genre_score giam dan.
    """
    chu_de_list = persona.get("chu_de", [])
    if not chu_de_list:
        return []

    theo_chu_de = {cd: [] for cd in chu_de_list}
    for a in articles:
        if a.get("genre") in theo_chu_de:
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


def _dinh_dang_danh_sach_tin(articles: list) -> str:
    ds = ""
    for i, a in enumerate(articles, 1):
        ds += (
            f"\n{i}. [{a.get('genre')}] {a.get('title')}\n"
            f"   Tóm tắt gốc: {a.get('summary')}\n"
        )
    return ds


MUC_DO_CHI_TIET = [
    "Viết thành MỘT ĐOẠN VĂN ĐẦY ĐỦ, tóm tắt trọn vẹn TẤT CẢ ý chính và ý phụ quan trọng của "
    "tin, có phân tích sâu, dùng thuật ngữ chuyên ngành phù hợp (tham khảo Ontology Context "
    "nếu có) — đây là phần TRỌNG TÂM của bài, mức độ chuyên sâu cao nhất.",
    "Viết thành MỘT ĐOẠN VĂN ĐẦY ĐỦ, tóm tắt trọn vẹn ý chính của tin (không bỏ sót ý quan "
    "trọng), có thể dùng thuật ngữ ngành nhưng không cần phân tích sâu như nhóm trọng tâm.",
    "Viết thành MỘT ĐOẠN VĂN ĐẦY ĐỦ, tóm tắt trọn vẹn ý chính của tin, ngôn ngữ phổ thông, "
    "không cần thuật ngữ chuyên ngành, nhưng vẫn phải nêu đủ nội dung cốt lõi (không chỉ "
    "nêu tên tin).",
]


def _muc_do_cho_tang(idx: int) -> str:
    return MUC_DO_CHI_TIET[min(idx, len(MUC_DO_CHI_TIET) - 1)]


def build_rss_prompt(persona: dict, ranked_articles: list, tin_gian_tiep: list = None) -> str:
    day_du = can_van_phong_day_du(persona, ranked_articles)
    ontology_ctx = lay_ontology_context_cho_nganh(_STATE_GRAPH, persona.get("nganh_to", ""))
    nhom_tin = nhom_tin_theo_chu_de(persona, ranked_articles)
    tin_gian_tiep = tin_gian_tiep or []

    opening_style = _chon_style(persona.get("id", ""), OPENING_STYLES)
    closing_style = _chon_style(persona.get("id", "") + "_close", CLOSING_STYLES)

    if day_du:
        yeu_cau_van_phong = (
            "Bài viết PHẢI bắt đầu bằng một dòng TIÊU ĐỀ in đậm, viết hoa hoặc in đậm, "
            "ngắn gọn, nêu khái quát chủ đề bản tin — đây là dòng đầu tiên của toàn văn bản, "
            "đứng TRƯỚC phần thân bài. Sau tiêu đề mới đến thân bài viết theo bố cục đầy đủ, "
            "chuyên nghiệp. Không cần đoạn tổng kết cuối bài trừ khi phong cách kết bài bên dưới yêu cầu."
        )
    else:
        yeu_cau_van_phong = (
            "Bài viết KHÔNG có tiêu đề — viết thẳng vào nội dung ngay từ câu/dòng đầu tiên, "
            "ngắn gọn, dễ đọc."
        )

    cam_cum_tu = ", ".join(f"'{p}'" for p in BANNED_PHRASES)

    ontology_section = ""
    if ontology_ctx:
        ontology_section = f"""
    PHẦN 1: KHUNG PHÂN TÍCH NGÀNH CÔNG VỤ (Ontology Context)
    {ontology_ctx}

    """

    tong_trong_so = sum(n["trong_so"] for n in nhom_tin) or 1.0
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
    {_dinh_dang_danh_sach_tin(tin_gian_tiep)}
    Yêu cầu:
        - Không cần mỗi tin một đoạn.
        - Hãy gộp các tin liên quan gần nhau thành một đoạn.
        - Trong mỗi tin chỉ giữ đúng ý quan trọng nhất (khoảng 1 câu).
        - Nếu nhiều tin nói về cùng một sự kiện hoặc cùng một chủ đề thì được phép gộp thành một câu hoặc một đoạn ngắn.
        - Mục tiêu là giúp người đọc nắm nhanh bối cảnh, không phải liệt kê toàn bộ.
    """

    prompt = f"""{ontology_section}Bạn đang viết một VĂN BẢN TÓM TẮT TIN TỨC CÁ NHÂN HÓA hàng ngày cho một người có hồ sơ sau:

        - Ngành/lĩnh vực: {persona.get('nganh_to')} - {persona.get('nganh_nho')}
        - Đơn vị công tác: {persona.get('to_chuc')}
        - Mô tả chung: {persona.get('mo_ta_chung')}

    {khoi_tin_text}
    {khoi_gian_tiep_text}

    Yêu cầu bắt buộc chung cho toàn bài:

    - CÁCH MỞ BÀI (áp dụng cho câu đầu tiên của đoạn văn ĐẦU TIÊN — tức là câu ngay sau tiêu đề
  nếu có tiêu đề, hoặc câu đầu văn bản nếu không có tiêu đề): {opening_style}

    - CÁCH KẾT BÀI (áp dụng cho đoạn văn CUỐI CÙNG, bắt buộc theo đúng kiểu này): {closing_style}

    - {yeu_cau_van_phong}

    - CẤU TRÚC BẮT BUỘC: MỖI TIN được viết thành MỘT ĐOẠN VĂN RIÊNG BIỆT, xuống dòng giữa các
      đoạn (mỗi đoạn tương ứng đúng 1 tin trong danh sách trên). KHÔNG gộp 2 tin trở lên vào
      cùng 1 đoạn. KHÔNG đặt tiêu đề kiểu "Tin 1:", KHÔNG gạch đầu dòng — đoạn văn tự nhiên,
      chỉ là xuống dòng phân tách rõ ràng giữa các tin để dễ quan sát.

    - Đoạn văn có thể mở đầu bằng một câu liên hệ ngắn tới đoạn trước nếu thấy tự nhiên,
      nhưng KHÔNG bắt buộc phải liền mạch xuyên suốt như một bài luận — ưu tiên tóm tắt đầy
      đủ, rõ ràng từng tin hơn là ưu tiên chuyển ý mượt giữa các tin.

    - TUYỆT ĐỐI KHÔNG dùng các cụm sau ở bất kỳ đâu trong bài: {cam_cum_tu}.

    - Không dùng quá 2 lần bất kỳ cụm chuyển đoạn nào trong toàn bài.

    - Đề cập nhóm ưu tiên cao trước, mức độ chi tiết giảm dần đúng theo thứ tự nhóm ở trên;
      nhóm tin liên quan gián tiếp (nếu có) luôn đặt ở cuối bài, sau tất cả nhóm chủ đề chính.

    - Đối với các tin thuộc chủ đề quan tâm:
        - Tin ảnh hưởng tới chính sách, pháp luật, kinh tế vĩ mô, ngân sách,
        quản lý nhà nước hoặc công việc hiện tại:
            -> tóm tắt đầy đủ.
        - Tin doanh nghiệp hoặc thị trường chỉ có ý nghĩa tham khảo:
            -> ngắn hơn.
        - Tin mang tính đời sống, giải trí hoặc cá nhân:
            -> chỉ giữ nếu có giá trị đặc biệt; nếu không thì bỏ.

    - ƯU TIÊN giữ lại các tin có giá trị thông tin cao. Nếu nhiều tin nói cùng một chủ đề, cùng một sự kiện hoặc có mức độ quan trọng thấp, được phép lược bỏ bớt hoặc gộp chúng thành một đoạn ngắn. Mục tiêu là tạo ra một bản tin dễ đọc, không phải liệt kê đầy đủ mọi tin. Các tin trong chu_de PHẢI tóm tắt đầy đủ ý chính (xem yêu cầu độ chi tiết riêng từng nhóm ở trên); các tin gián tiếp tóm sơ ý chính nhất nhưng vẫn phải có nội dung, không được chỉ nêu tên tin suông.

    - Cố gắng bao quát các tin trong danh sách.  Nếu nhiều tin trùng chủ đề hoặc mức độ quan trọng thấp, được phép gộp hoặc lược bỏ các chi tiết phụ.

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


def tom_tat_rss_cho_persona(persona: dict, articles: list, client,
                            model_name: str = SUMMARY_MODEL_NAME) -> dict:
    ranked = xep_hang_bai_cho_persona(persona, articles)

    if not ranked:
        return {
            "id": persona.get("id"),
            "summary": "",
            "ranked_articles": [],
            "note": "Không có tin nào khớp chu_de của persona này.",
        }

    nhom_tin = nhom_tin_theo_chu_de(persona, ranked)
    tin_gian_tiep = tim_tin_lien_quan_gian_tiep(persona, articles, ranked)

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

    summary = response.text.strip()

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

    ket_qua = {
        "id": persona.get("id"),
        "summary": summary,
        "so_luong_tin_da_dua_vao": so_bai,
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

    with open(DATA_DIR / "vnexpress_rss_snapshot_2707.json", encoding="utf-8") as f:
        articles = json.load(f)

    with open(DATA_DIR / "profile" / "state_profiles_enrich_sample.json", encoding="utf-8") as f:
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