"""
pipeline/rss_personalize.py

Buoc 3 - RSS extension: chon loc + xep hang tin RSS theo persona (state_profiles),
roi goi LLM viet tom tat ca nhan hoa.

Luu y: file nay TU PHAN LOAI GENRE RIENG, khong dung chung ham voi
pipeline/content_classifier.py, vi van ban dau vao khac nhau
(bai bao RSS dai vs mo ta persona ngan) nen can nguong/logic tinh diem rieng.
"""

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

from pipeline.utils import retry_generate, SUMMARY_MODEL_NAME, load_graph
from pipeline.rss.ontology_context_state import lay_ontology_context_cho_nganh

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
CANDIDATE_POOL_SIZE = 20  # so bai toi da dua vao prompt de LLM tu can nhac cat bot
UOC_LUONG_TU_2_TRANG_A4 = 1300  # uoc luong ~650 tu/trang, size chu 13, dan dong 1.5 - CAN XAC NHAN LAI
MAX_OUTPUT_TOKENS = 4096

TY_LE_TU_COT_LOI = 0.65   # % độ dài dành cho tin đúng chuyên môn (chu_de chính)
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

GIOI_HAN_TIN_GIAN_TIEP = 3  # so tin toi da o tier "lien quan gian tiep", chi tom so qua


def tim_tin_lien_quan_gian_tiep(persona: dict, articles: list, da_chon: list,
                                 gioi_han: int = GIOI_HAN_TIN_GIAN_TIEP) -> list:
    """
    Tim tin NGOAI chu_de cua persona nhung co overlap gian tiep (theo
    config/genre_overlap.json) voi it nhat 1 chu_de cua persona, vuot
    nguong NGUONG_LIEN_QUAN_GIAN_TIEP. Dung rieng cho tier "tom so qua",
    khong tinh vao top_n chinh cua xep_hang_bai_cho_persona.
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

    ung_vien.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in ung_vien[:gioi_han]]

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


def xep_hang_bai_cho_persona(persona: dict, articles: list, top_n: int = 5) -> list:
    """
    Loc va xep hang bai RSS cho persona. Dam bao MOI chu_de cua persona co
    dai dien trong ket qua (theo quota ty le trong so vi tri), thay vi de
    chu_de chinh chiem het top_n neu no co qua nhieu bai kha dung.
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

    trong_so = [_weight_of_chu_de(i) for i in range(len(chu_de_list))]
    tong_trong_so = sum(trong_so)
    quotas = [round(top_n * w / tong_trong_so) for w in trong_so]

    da_chon, da_chon_id = [], set()
    for cd, quota in zip(chu_de_list, quotas):
        for a in theo_chu_de[cd][:quota]:
            da_chon.append(a)
            da_chon_id.add(id(a))

    # neu chu_de nao khong du bai de lap day quota, lay bu tu cac bai con
    # du cua chu_de khac theo thu tu (trong so vi tri, genre_score)
    if len(da_chon) < top_n:
        con_du = []
        for i, cd in enumerate(chu_de_list):
            for a in theo_chu_de[cd]:
                if id(a) not in da_chon_id:
                    con_du.append((trong_so[i], a.get("genre_score", 0.0), a))
        con_du.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for w, s, a in con_du[: top_n - len(da_chon)]:
            da_chon.append(a)
            da_chon_id.add(id(a))

    def _vi_tri_trong_so(a):
        genre = a.get("genre")
        idx = chu_de_list.index(genre) if genre in chu_de_list else len(chu_de_list)
        return _weight_of_chu_de(idx)

    da_chon.sort(key=lambda a: (_vi_tri_trong_so(a), a.get("genre_score", 0.0)), reverse=True)
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
    "Viết chi tiết, phân tích sâu, dùng thuật ngữ chuyên ngành (tham khảo Ontology Context "
    "nếu có), đây là phần TRỌNG TÂM của bài — mức độ chuyên sâu cao nhất.",
    "Viết với mức độ chi tiết vừa phải, có thể dùng thuật ngữ ngành nhưng không cần phân tích "
    "sâu, đóng vai trò bổ trợ cho phần trọng tâm.",
    "Chỉ lướt qua ngắn gọn (1-2 câu), ngôn ngữ phổ thông, không cần thuật ngữ chuyên ngành, "
    "mang tính thông tin nền.",
]


def _muc_do_cho_tang(idx: int) -> str:
    return MUC_DO_CHI_TIET[min(idx, len(MUC_DO_CHI_TIET) - 1)]


def build_rss_prompt(persona: dict, ranked_articles: list, tin_gian_tiep: list = None) -> str:
    day_du = can_van_phong_day_du(persona, ranked_articles)
    ontology_ctx = lay_ontology_context_cho_nganh(persona.get("nganh_to", ""))

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
        do_dai_nhom = round(UOC_LUONG_TU_2_TRANG_A4 * n["trong_so"] / tong_trong_so)
        khuynh_huong = ""
        if idx == 0:
            khuynh_huong = (
                f"\n- KHUYNH HƯỚNG PHÂN TÍCH BẮT BUỘC cho nhóm này: chủ động chọn góc nhìn, "
                f"số liệu, hệ quả liên quan TRỰC TIẾP tới định hướng công việc sau đây, để nó "
                f"DẪN DẮT cách bạn diễn giải các tin trong nhóm: "
                f"\"{persona.get('cau_hoi_truoc_mat', '')}\""
            )
        khoi_tin_text += f"""
    NHÓM CHỦ ĐỀ "{n['chu_de']}" (ưu tiên thứ {idx + 1}, khoảng {do_dai_nhom} từ):
    {_dinh_dang_danh_sach_tin(n['bai'])}
    Yêu cầu: {_muc_do_cho_tang(idx)}{khuynh_huong}
    """

    khoi_gian_tiep_text = ""
    if tin_gian_tiep:
        khoi_gian_tiep_text = f"""
    NHÓM TIN LIÊN QUAN GIÁN TIẾP (ngoài chủ đề chính của người này, nhưng có liên hệ nhẹ,
    khoảng {round(UOC_LUONG_TU_2_TRANG_A4 * 0.08)} từ TỔNG CỘNG cho cả nhóm này):
    {_dinh_dang_danh_sach_tin(tin_gian_tiep)}
    Yêu cầu: CHỈ nhắc thoáng qua, mỗi tin tối đa 1 câu, ngôn ngữ phổ thông, không phân tích,
    không dùng thuật ngữ chuyên ngành, không liên hệ khuynh hướng công việc. Đặt ở cuối bài,
    không lồng vào giữa các nhóm chủ đề chính.
    """

    prompt = f"""{ontology_section}Bạn đang viết một VĂN BẢN TÓM TẮT TIN TỨC CÁ NHÂN HÓA hàng ngày cho một người có hồ sơ sau:

        - Ngành/lĩnh vực: {persona.get('nganh_to')} - {persona.get('nganh_nho')}
        - Đơn vị công tác: {persona.get('to_chuc')}
        - Mô tả chung: {persona.get('mo_ta_chung')}

    {khoi_tin_text}
    {khoi_gian_tiep_text}

    Yêu cầu bắt buộc chung cho toàn bài:
    - - CÁCH MỞ BÀI (áp dụng cho câu đầu tiên của PHẦN THÂN BÀI — tức là câu ngay sau tiêu đề nếu
  có tiêu đề, hoặc câu đầu văn bản nếu không có tiêu đề; không quyết định việc có/không có
  tiêu đề, việc đó đã được quy định riêng ở trên): {opening_style}
    - CÁCH KẾT BÀI (bắt buộc theo đúng kiểu này): {closing_style}
    - {yeu_cau_van_phong}
    - TUYỆT ĐỐI KHÔNG dùng các cụm sau ở bất kỳ đâu trong bài: {cam_cum_tu}.
    - Không dùng quá 2 lần bất kỳ cụm chuyển đoạn nào trong toàn bài.
    - Viết thành MỘT VĂN BẢN LIỀN MẠCH — các nhóm chủ đề phải lồng ghép, chuyển ý tự nhiên,
      KHÔNG tách rời kiểu "Chủ đề 1... Chủ đề 2...", KHÔNG liệt kê "Tin 1: ...", KHÔNG gạch đầu dòng.
    - Đề cập nhóm ưu tiên cao trước, mức độ chi tiết giảm dần đúng theo thứ tự nhóm ở trên;
      nhóm tin liên quan gián tiếp (nếu có) chỉ nhắc ở cuối bài.
    - Tổng độ dài toàn bài khoảng {UOC_LUONG_TU_2_TRANG_A4} từ — đây là MỤC TIÊU THAM KHẢO, không phải giới hạn cứng. Thứ tự ưu tiên khi viết:
  1) Viết ĐẦY ĐỦ, KHÔNG cắt xén nội dung của nhóm ưu tiên cao nhất (chu_de chính) — được phép vượt quá tổng độ dài mục tiêu tối đa khoảng 15% nếu cần để hoàn thành trọn vẹn nhóm này.
  2) Nếu cần rút ngắn để tổng độ dài không vượt quá nhiều, HÃY BỎ BỚT nội dung theo thứ tự: nhóm liên quan gián tiếp trước, rồi đến nhóm chủ đề ưu tiên thấp nhất.
  3) TUYỆT ĐỐI KHÔNG dừng đột ngột giữa câu hoặc giữa một tin đang viết dở — nếu phải bỏ một tin, hãy bỏ nguyên cả tin đó ngay từ đầu, không viết dở dang.
    - Không bịa thêm thông tin ngoài các tin đã cho.
    - Chỉ trả về nội dung văn bản, không thêm lời dẫn kiểu "Dưới đây là...".
    """.strip()

    return prompt


def tom_tat_rss_cho_persona(persona: dict, articles: list, client,
                            model_name: str = SUMMARY_MODEL_NAME) -> dict:
    ranked = xep_hang_bai_cho_persona(persona, articles, top_n=CANDIDATE_POOL_SIZE)

    if not ranked:
        return {
            "id": persona.get("id"),
            "summary": "",
            "ranked_articles": [],
            "note": "Không có tin nào khớp chu_de của persona này.",
        }

    nhom_tin = nhom_tin_theo_chu_de(persona, ranked)
    note = None
    if not nhom_tin or nhom_tin[0]["chu_de"] != persona.get("chu_de", [""])[0]:
        note = (
            f"Không có tin nào khớp đúng chủ đề chuyên môn chính "
            f"(\"{persona.get('chu_de', [''])[0]}\") trong đợt tin này."
        )

    tin_gian_tiep = tim_tin_lien_quan_gian_tiep(persona, articles, ranked)

    prompt = build_rss_prompt(persona, ranked, tin_gian_tiep)

    def _call():
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.0,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
            },
        )

    response = retry_generate(_call)

    bi_cat_cut = False
    try:
        finish_reason = str(response.candidates[0].finish_reason)
        if "MAX_TOKENS" in finish_reason:
            bi_cat_cut = True
    except (AttributeError, IndexError):
        pass  # khong doc duoc finish_reason thi bo qua, khong chan pipeline

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
            f"{MAX_OUTPUT_TOKENS} token — cần kiểm tra lại và có thể chạy lại "
            f"persona này riêng."
        )

    ket_qua = {
        "id": persona.get("id"),
        "summary": summary,
        "ranked_articles": [
            {"title": a["title"], "genre": a["genre"], "genre_score": a["genre_score"], "link": a.get("link")}
            for a in ranked
        ],
        "tin_gian_tiep": [
            {"title": a["title"], "genre": a["genre"],"genre_score": a["genre_score"], "link": a.get("link")}
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

        print(f"[{persona['id']}] xong, mất {time.time()-t0:.1f}s")
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

            print(f"[{persona_id}] xong, mất {time.time()-t0:.1f}s")
            print("=================================")

        print(
            "\nXONG HẾT. Tổng thời gian:",
            round((time.time() - t_bat_dau) / 60, 1),
            "phút"
        )