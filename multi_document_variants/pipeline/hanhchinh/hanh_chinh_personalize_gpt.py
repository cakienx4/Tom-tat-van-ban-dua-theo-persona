import json
import re
import asyncio
from pathlib import Path

from pipeline.utils import (
    retry_generate_async, OSS_MODEL_NAME, load_graph, tao_oss_client_async,
    OSS_MAX_CONCURRENCY_SUMMARY, uoc_luong_so_token,
)
from pipeline.profiles.ontology_context_state import lay_ontology_context_cho_nganh

ROOT_DIR = Path(__file__).resolve().parents[2]
_ONTOLOGY_PATH = ROOT_DIR / "persona_states.ttl"
_STATE_GRAPH = load_graph(str(_ONTOLOGY_PATH))
HANH_CHINH_MAX_OUTPUT_TOKENS = 3200
HANH_CHINH_MAX_OUTPUT_TOKENS_MO_RONG = 6000
NGUONG_TOKEN_MOI_BATCH_MUC = 1800
OSS_CONTEXT_LIMIT = 8192
AN_TOAN_TOKEN_DU = 400

GIAI_THICH_TU_VIET_TAT = {
    "UBND": "Ủy ban nhân dân",
    "HĐND": "Hội đồng nhân dân",
    "BHXH": "Bảo hiểm xã hội",
    "BHYT": "Bảo hiểm y tế",
    "UBMTTQ": "Ủy ban Mặt trận Tổ quốc",
    "GD&ĐT": "Giáo dục và Đào tạo",
    "BGDĐT": "Bộ Giáo dục và Đào tạo",
    "GDNN-GDTX": "Giáo dục nghề nghiệp - Giáo dục thường xuyên",
    "CBCCVC": "cán bộ, công chức, viên chức",
    "TTHC": "thủ tục hành chính",
    "TTg": "Thủ tướng Chính phủ",
    "NĐ-CP": "Nghị định của Chính phủ",
    "NQ/TW": "Nghị quyết của Trung ương Đảng",
    "NQ-HĐND": "Nghị quyết của Hội đồng nhân dân",
    "PCCC": "phòng cháy, chữa cháy",
    "CNCH": "cứu nạn, cứu hộ",
}

GIAI_THICH_THUAT_NGU_HANH_CHINH = {
    "sáp nhập": "sáp nhập (gộp lại thành một)",
    "hợp nhất": "hợp nhất (gộp thành một đơn vị duy nhất)",
    "đề án": "đề án (kế hoạch, phương án chi tiết)",
    "phân cấp": "phân cấp (giao bớt quyền, trách nhiệm xuống cấp dưới)",
    "thẩm định": "thẩm định (kiểm tra, xét duyệt)",
    "xã hội hóa": "xã hội hóa (huy động nguồn lực ngoài ngân sách nhà nước)",
    "tinh giản biên chế": "tinh giản biên chế (giảm bớt số lượng cán bộ, nhân sự)",
    "tinh gọn": "tinh gọn (thu gọn, giảm bớt đầu mối)",
    "quy hoạch tổng thể": "quy hoạch tổng thể (kế hoạch bố trí không gian dài hạn)",
}


def _bo_sung_giai_thich_tu_viet_tat(text):
    for tu, day_du in {**GIAI_THICH_TU_VIET_TAT, **GIAI_THICH_THUAT_NGU_HANH_CHINH}.items():
        if tu not in text:
            continue
        if day_du.lower() in text.lower():
            continue
        if re.search(rf"{re.escape(tu)}\s*\(", text):
            continue
        text = re.sub(
            rf"(?<![\wÀ-ỹ]){re.escape(tu)}(?![\wÀ-ỹ])",
            f"{tu} ({day_du})",
            text,
            count=1,
        )
    return text

_MAU_VIET_TAT_TIENG_VIET = re.compile(
    r"(?<![\wÀ-ỹ])([A-ZĐƯ]{2,6}(?:[&\-/][A-ZĐƯ0-9]{1,6}){0,3})(?![\wÀ-ỹ])"
)

_LOAI_TRU_KHONG_PHAI_VIET_TAT = {
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
}


def _viet_tat_xuat_hien_trong_batch(danh_sach_muc, style):
    tim_thay = set()
    for muc in danh_sach_muc:
        tang = muc.get("tang_do_sau", TANG_NEN)
        can_giai_thich = tang == TANG_TRUNG_BINH or (
            tang == TANG_NEN and style in ("binh_thuong", "khong_chuyen_mon")
        )
        if not can_giai_thich:
            continue
        noi_dung = " ".join(muc.get("doan_van", [])) + " " + (muc.get("heading") or "")
        for m in _MAU_VIET_TAT_TIENG_VIET.finditer(noi_dung):
            tu = m.group(1)
            if tu in _LOAI_TRU_KHONG_PHAI_VIET_TAT:
                continue
            tim_thay.add(tu)
    return sorted(tim_thay)

def _batch_can_giai_thich(batch_muc, style):
    for muc in batch_muc:
        tang = muc.get("tang_do_sau", TANG_NEN)
        if tang == TANG_TRUNG_BINH:
            return True
        if tang == TANG_NEN and style in ("binh_thuong", "khong_chuyen_mon"):
            return True
    return False

def _tinh_max_output_token_an_toan(so_token_prompt, cap_mong_muon):
    con_lai = OSS_CONTEXT_LIMIT - so_token_prompt - AN_TOAN_TOKEN_DU
    return max(512, min(cap_mong_muon, con_lai))


TANG_CHUYEN_SAU = 0
TANG_TRUNG_BINH = 1
TANG_NEN = 2


def _chi_so_da_khop_persona(persona_id, ket_qua_khop_persona):
    ket_qua = {}
    for entry in ket_qua_khop_persona:
        if persona_id not in entry.get("danh_sach_persona_id_khop", []):
            continue

        chi_so_goc = entry.get("chi_so_doi_tuong_goc")
        if chi_so_goc is None:
            continue

        do_tin_cay = entry.get("do_tin_cay", "thap")

        if do_tin_cay == "trung bình" and persona_id in entry.get(
                "danh_sach_persona_id_khop_ca_nganh_nho", []
        ):
            do_tin_cay = "cao"

        ket_qua[chi_so_goc] = do_tin_cay
    return ket_qua


def gan_tang_do_sau_va_style(persona_id, danh_sach_muc, ket_qua_khop_persona):
    chi_so_theo_do_tin_cay = _chi_so_da_khop_persona(persona_id, ket_qua_khop_persona)

    co_cao = "cao" in chi_so_theo_do_tin_cay.values()
    co_trung_binh = "trung bình" in chi_so_theo_do_tin_cay.values()

    if co_cao:
        style = "chuyen_sau"
    elif co_trung_binh:
        style = "khong_chuyen_mon"
    else:
        style = "binh_thuong"

    danh_sach_muc_moi = []
    for muc in danh_sach_muc:
        chi_so_lien_quan = muc.get("chi_so_doi_tuong_lien_quan", [])
        do_tin_cay_cua_muc = [
            chi_so_theo_do_tin_cay[cs] for cs in chi_so_lien_quan
            if cs in chi_so_theo_do_tin_cay
        ]

        if "cao" in do_tin_cay_cua_muc:
            tang = TANG_CHUYEN_SAU
        elif "trung bình" in do_tin_cay_cua_muc:
            tang = TANG_TRUNG_BINH
        else:
            tang = TANG_NEN

        muc_moi = dict(muc)
        muc_moi["tang_do_sau"] = tang
        danh_sach_muc_moi.append(muc_moi)

    return danh_sach_muc_moi, style



GOP_MUC_NEN_THEO_STYLE = {
    "chuyen_sau": (
        "- KHÔNG gộp các mục tầng nền lại với nhau. Mỗi mục (kể cả mục tầng "
        "nền) vẫn có đoạn/câu riêng theo đúng yêu cầu của tầng đã ghi ngay tại "
        "dòng của mục đó - tức là VẪN GIỮ số liệu/mốc thời gian/tên đơn vị cụ "
        "thể của mục đó, không tóm chung chung, không cắt bỏ chi tiết."
    ),
    "khong_chuyen_mon": (
        "- KHÔNG gộp các mục tầng nền lại với nhau. Mỗi mục (kể cả mục tầng "
        "nền) vẫn có đoạn/câu riêng theo đúng yêu cầu của tầng đã ghi ngay tại "
        "dòng của mục đó - tức là VẪN GIỮ số liệu/mốc thời gian/tên đơn vị cụ "
        "thể của mục đó, không tóm chung chung, không cắt bỏ chi tiết."
    ),
    "binh_thuong": (
        "- Không bắt buộc viết một đoạn văn tách biệt cho MỌI mục: nếu nhiều mục "
        "LIÊN TIẾP NHAU (đứng ngay cạnh nhau trong danh sách trên, KHÔNG có mục "
        "khác xen giữa) cùng thuộc tầng \"nền\" và có nội dung gần nhau, CÓ THỂ "
        "gộp chung thành một đoạn cho mạch văn tự nhiên.\n"
        "  TUYỆT ĐỐI KHÔNG được gộp các mục theo kiểu \"cùng chủ đề\" nếu chúng "
        "KHÔNG liên tiếp nhau trong danh sách - dù 2 mục nội dung giống nhau "
        "(vd đều nói về trường cao đẳng, đều nói về trung tâm GDNN-GDTX) nhưng "
        "đứng CÁCH XA nhau (có mục khác xen giữa) thì PHẢI viết theo đúng vị trí "
        "gốc của từng mục, KHÔNG được kéo chúng lại gần nhau thành 1 cụm.\n"
        "  Sai: mục thứ ba nói về trường cao đẳng A, mục thứ tư nói về trung tâm "
        "GDNN-GDTX B, mục thứ năm lại nói tiếp về trường cao đẳng C - nhưng bài "
        "viết gộp mục ba và mục năm (2 trường cao đẳng) thành 1 đoạn viết trước, "
        "rồi mới nhắc tới mục bốn (trung tâm GDNN-GDTX) sau.\n"
        "  Đúng: viết đúng trình tự mục ba, rồi mục bốn, rồi mục năm - dù mục ba "
        "và mục năm cùng nói về trường cao đẳng.\n"
        "  Việc gộp KHÔNG được đánh đổi lấy việc bỏ sót nội dung: đoạn gộp đó vẫn "
        "PHẢI phản ánh đầy đủ các nhóm nội dung chính của TẤT CẢ các mục được gộp "
        "(mục tiêu, yêu cầu, nhiệm vụ, phương án... nếu có), theo đúng thứ tự so "
        "với văn bản gốc. Không có yêu cầu phải viết ngắn - độ dài do nội dung "
        "cần bao quát quyết định."
    ),
}



SO_MUC_TOI_DA_MOI_BATCH = 4

TEN_TANG_HIEN_THI = {
    TANG_CHUYEN_SAU: "CHUYÊN SÂU",
    TANG_TRUNG_BINH: "TRUNG BÌNH",
    TANG_NEN: "NỀN",
}

YEU_CAU_NGAN_THEO_TANG = {
    TANG_CHUYEN_SAU: (
        "tóm ĐẦY ĐỦ, giữ nguyên nhiệm vụ cụ thể/tên cơ quan/số liệu/mốc thời "
        "gian thực tế, dùng thuật ngữ tự nhiên KHÔNG cần giải thích, KHÔNG ghi "
        "số hiệu văn bản viện dẫn"
    ),
    TANG_TRUNG_BINH: (
        "bao quát nội dung chính, ngôn ngữ phổ thông, PHẢI giải thích ngắn gọn "
        "mọi thuật ngữ/từ viết tắt hành chính-pháp lý ngay trong câu"
    ),
}

YEU_CAU_NGAN_TANG_NEN_THEO_STYLE = {
    "chuyen_sau": (
        "bao quát đầy đủ, giữ số liệu/mốc thời gian/tên đơn vị, KHÔNG gộp với "
        "mục khác, thuật ngữ dùng tự nhiên không cần giải thích"
    ),
    "khong_chuyen_mon": (
        "bao quát đầy đủ, giữ số liệu/mốc thời gian/tên đơn vị, KHÔNG gộp với "
        "mục khác, PHẢI giải thích thuật ngữ/từ viết tắt"
    ),
    "binh_thuong": (
        "bao quát đầy đủ, CÓ THỂ gộp với mục nền liền kề cùng chủ đề theo đúng "
        "thứ tự (không bỏ sót mục nào), PHẢI giải thích thuật ngữ/từ viết tắt"
    ),
}


def _yeu_cau_ngan(tang, style):
    if tang == TANG_NEN:
        return YEU_CAU_NGAN_TANG_NEN_THEO_STYLE.get(style, YEU_CAU_NGAN_TANG_NEN_THEO_STYLE["binh_thuong"])
    return YEU_CAU_NGAN_THEO_TANG[tang]


_THU_TU_VN = [
    "thứ nhất", "thứ hai", "thứ ba", "thứ tư", "thứ năm",
    "thứ sáu", "thứ bảy", "thứ tám", "thứ chín", "thứ mười",
]


def _ten_thu_tu(i):
    if 1 <= i <= len(_THU_TU_VN):
        return _THU_TU_VN[i - 1]
    return f"thứ {i}"

_MAU_SO_THU_TU_DAU_HEADING = re.compile(
    r"^\s*(?:\d{1,2}(?:\.\d{1,2}){0,3}\.?|[IVXLCDM]{1,5}\.)\s*[-:]?\s*"
)


def _lam_sach_so_thu_tu_dau_heading(heading):
    if not heading:
        return heading
    da_sach = _MAU_SO_THU_TU_DAU_HEADING.sub("", heading, count=1).strip()
    return da_sach or heading

def _dinh_dang_danh_sach_muc(danh_sach_muc, style):
    ds = ""
    for i, muc in enumerate(danh_sach_muc, 1):
        if muc.get("heading") is None and not muc.get("doan_van"):
            continue
        noi_dung = "\n   ".join(muc.get("doan_van", []))
        tang = muc.get("tang_do_sau", TANG_NEN)
        heading_sach = _lam_sach_so_thu_tu_dau_heading(muc.get("heading"))
        ds += (
            f"\nMục {_ten_thu_tu(i)} (nhãn vị trí, KHÔNG chép vào bài viết): \n"
            f"   Tiêu đề gốc (đã bỏ số thứ tự nếu có): "
            f"\"{heading_sach or '(không có tiêu đề riêng)'}\"\n"
            f"   Nội dung: {noi_dung}\n"
            f"   Tầng {TEN_TANG_HIEN_THI[tang]}: {_yeu_cau_ngan(tang, style)}\n"
        )
    return ds

def _chia_muc_theo_token(danh_sach_muc, style):
    batches = []
    batch_hien_tai = []

    for muc in danh_sach_muc:
        ung_vien = batch_hien_tai + [muc]
        token_ung_vien = uoc_luong_so_token(_dinh_dang_danh_sach_muc(ung_vien, style))
        vuot_token = batch_hien_tai and token_ung_vien > NGUONG_TOKEN_MOI_BATCH_MUC
        vuot_so_luong = len(ung_vien) > SO_MUC_TOI_DA_MOI_BATCH

        if batch_hien_tai and (vuot_token or vuot_so_luong):
            batches.append(batch_hien_tai)
            batch_hien_tai = []

        batch_hien_tai.append(muc)

    if batch_hien_tai:
        batches.append(batch_hien_tai)

    return batches


def build_hanh_chinh_prompt(persona, ket_qua_extract, danh_sach_muc_voi_tang, style):
    loai_van_ban = ket_qua_extract.get("loai_van_ban", "")
    ontology_ctx = lay_ontology_context_cho_nganh(persona.get("nganh_to", ""))

    danh_sach_muc_text = _dinh_dang_danh_sach_muc(danh_sach_muc_voi_tang, style)
    quy_tac_gop_muc_nen = GOP_MUC_NEN_THEO_STYLE.get(
        style, GOP_MUC_NEN_THEO_STYLE["binh_thuong"]
    )

    danh_sach_viet_tat = _viet_tat_xuat_hien_trong_batch(danh_sach_muc_voi_tang, style)
    checklist_viet_tat = ""
    if danh_sach_viet_tat:
        checklist_viet_tat = (
            "\n    DANH SÁCH VIẾT TẮT XUẤT HIỆN TRONG ĐỢT NÀY (dò tự động từ văn bản gốc): "
            + ", ".join(danh_sach_viet_tat)
            + ". Với MỖI từ trong danh sách này, ở lần đầu xuất hiện trong đoạn thuộc tầng cần "
            "giải thích, BẮT BUỘC chèn giải thích ngắn gọn ngay trong câu (dựa vào kiến thức "
            "hành chính/pháp lý bạn đã biết về loại viết tắt này trong văn bản nhà nước Việt "
            "Nam - ví dụ PCCC thường là 'phòng cháy, chữa cháy', CNCH thường là 'cứu nạn, cứu "
            "hộ'). Nếu không chắc chắn 100% nghĩa đầy đủ, vẫn PHẢI viết ra cách hiểu gần đúng "
            "nhất về chức năng/ý nghĩa của viết tắt đó trong ngữ cảnh - TUYỆT ĐỐI KHÔNG được để "
            "viết tắt đứng một mình không có bất kỳ giải thích nào chỉ vì không chắc chắn tuyệt "
            "đối. Trước khi trả lời, rà lại TỪNG từ trong danh sách này xem đã giải thích chưa."
        )

    ontology_section = ""
    if ontology_ctx:
        ontology_section = f"""
    PHẦN 1: KHUNG PHÂN TÍCH NGÀNH CÔNG VỤ (Ontology Context)
    {ontology_ctx}

    """

    prompt = f"""{ontology_section}Bạn đang tóm tắt cá nhân hóa 1 văn bản hành chính (loại: {loai_van_ban})
    cho một cán bộ có hồ sơ công vụ sau:

    - Ngành/lĩnh vực: {persona.get('nganh_to')} - {persona.get('nganh_nho')}
    - Đơn vị công tác: {persona.get('to_chuc')}
    - Mô tả chung: {persona.get('mo_ta_chung')}

    Dưới đây là một phần nội dung văn bản (văn bản dài nên được xử lý theo từng đợt
    liên tiếp), đã chia theo mục, GIỮ NGUYÊN THỨ TỰ như văn bản gốc. Mỗi mục có ghi
    rõ yêu cầu riêng ngay sau nội dung của nó - PHẢI tuân thủ đúng yêu cầu đó cho
    TỪNG mục, không viết đều tay như nhau cho tất cả các mục kể cả về độ dài lẫn
    cách dùng từ ngữ:
    {danh_sach_muc_text}

    QUY TẮC BẮT BUỘC:
    - Viết thành bài tóm tắt liền mạch, TUYỆT ĐỐI giữ ĐÚNG THỨ TỰ các mục như văn
      bản gốc đã liệt kê ở trên - KHÔNG được đảo thứ tự, KHÔNG được đưa mục nào
      lên trước dù mục đó có tầng độ sâu cao hơn mục khác.
    - ĐỊNH DẠNG ĐẦU RA LÀ VĂN XUÔI THUẦN TÚY, KHÔNG CÓ NGOẠI LỆ, áp dụng cho MỌI
      văn bản bất kể số lượng mục nhiều hay ít, văn bản dài hay ngắn:
      + TUYỆT ĐỐI KHÔNG đánh số hoặc đặt tiêu đề cho mục dưới bất kỳ hình thức
        nào - kể cả "Mục 1:", "1.", "(1)", "Về mục thứ nhất:", in đậm tên mục,
        hay lặp lại nguyên văn heading gốc của mục làm câu mở đầu đoạn.
      + TUYỆT ĐỐI KHÔNG dùng gạch đầu dòng, danh sách liệt kê máy móc.
      + Sai (không được viết): "1. Về công tác an toàn thực phẩm: UBND yêu cầu..."
      + Đúng (phải viết): "Về công tác an toàn thực phẩm, UBND yêu cầu..." hoặc
        chuyển thẳng sang nội dung bằng câu dẫn tự nhiên, không tách dòng riêng
        cho từng mục.
      + Một dạng hay bị sót: chép lại GẦN NHƯ NGUYÊN VĂN tiêu đề mục (kể cả
        khi đặt trong ngoặc kép) làm câu mở đoạn.
        Sai: "Trong phần Mục đích, yêu cầu, UBND xác định..." (nếu viết kèm
        số/ký hiệu phía trước như "1. Mục đích, yêu cầu" thì càng sai nặng).
        Sai: "Về 2. Đề nghị Ban Tổ chức Thành ủy, cơ quan cần..."
        Đúng: "UBND xác định mục đích, yêu cầu của kế hoạch là..." (viết lại
        hoàn toàn bằng câu dẫn tự nhiên của riêng bạn, không dùng lại cụm số
        thứ tự + tên mục nguyên văn dưới bất kỳ hình thức nào).
      + Quy tắc này ĐÚNG NGUYÊN VẸN với mọi văn bản, không được nới lỏng chỉ vì
        văn bản có nhiều mục hoặc mục dài - càng nhiều mục càng phải viết liền
        mạch bằng câu dẫn chuyển ý, không phải bằng cách đánh số.
    - Với MỖI mục, tuân thủ ĐÚNG yêu cầu đã ghi ngay sau nội dung của mục đó
      ("Tầng ...: ...") - lưu ý yêu cầu này khác nhau tùy theo tầng VÀ tùy theo
      hồ sơ người đọc, không áp một kiểu viết chung cho tất cả các mục.
    - Dù batch này có nhiều mục, KHÔNG được viết theo kiểu "gom theo chủ đề" (kể
      lại các mục có chủ đề giống nhau nhưng nằm ở vị trí khác nhau trong danh
      sách thành một cụm chung) - PHẢI đi tuần tự đúng theo đúng thứ tự (mục
      thứ nhất, thứ hai, thứ ba...) đã liệt kê ở trên, chỉ được gộp các mục nền
      LIÊN TIẾP theo đúng quy tắc dưới đây, không được gộp các mục cách xa nhau
      trong danh sách.
    - BẮT BUỘC ÁP DỤNG QUY TẮC GỘP/KHÔNG GỘP MỤC TẦNG NỀN SAU ĐÂY, TUYỆT ĐỐI
      KHÔNG được làm khác:
    {quy_tac_gop_muc_nen}
    - KHÔNG tự suy luận, đánh giá hoặc thêm nhận định không có trong văn bản gốc.
    - KHÔNG chèn bất kỳ câu/cụm chú thích nào về quá trình viết bài (ví dụ:
      "(mục này được tóm gọn vì...)"). Bài trả về chỉ là văn bản tóm tắt tự nhiên.
    - Chỉ trả về nội dung văn bản, không thêm lời dẫn kiểu "Dưới đây là...".
    - QUY TẮC VỀ SỐ LIỆU:
      + CHỈ giữ các số liệu phản ánh nội dung thực tế của văn bản, bao gồm:
        * tỷ lệ, phần trăm;
        * số lượng cơ quan, đơn vị, trường học, cán bộ, người dân...;
        * chỉ tiêu, mục tiêu, kết quả;
        * kinh phí, diện tích, quy mô;
        * ngày, tháng, năm;
        * thời hạn, lộ trình, giai đoạn thực hiện;
        * các số liệu thống kê và thông tin định lượng phục vụ nội dung văn bản.
      + TUYỆT ĐỐI KHÔNG giữ hoặc nhấn mạnh số hiệu văn bản hành chính, bao gồm
        số quyết định, số công văn, số kế hoạch, số thông báo, số báo cáo, số
        nghị quyết, số chỉ thị hoặc bất kỳ chuỗi ký hiệu dạng
        "xxx/TTg-...", "xxx/QĐ-...", "xxx/KH-...", "xxx/CV-...",
        "xxx/UBND-...",...
      + Nếu câu chỉ khác nhau ở số hiệu văn bản thì bỏ số hiệu, giữ lại nội
        dung chính của câu.
      + Ví dụ:
          Sai: "Kế hoạch số 1186/KH-BGDĐT quy định..."
          Đúng: "Kế hoạch quy định..."
          Sai: "Quyết định số 777/TTg-TCCV yêu cầu..."
          Đúng: "Quyết định yêu cầu..."
          Đúng: "Thực hiện tinh gọn tối thiểu 50% đầu mối."
          Đúng: "Lộ trình sắp xếp 10 trường cao đẳng."
          Đúng: "Hoàn thành trước ngày 31/12/2026."
    - QUY TẮC GIẢI THÍCH THUẬT NGỮ (áp dụng cho đoạn thuộc tầng "trung bình",
      và tầng "nền" khi style tổng thể là "khong_chuyen_mon" hoặc "binh_thuong" -
      tức các đoạn dành cho người đọc KHÔNG có chuyên môn đúng lĩnh vực đó):
      + BẮT BUỘC mọi thuật ngữ hành chính, pháp lý hoặc chuyên ngành xuất hiện
        trong đoạn đó phải có phần giải thích ngắn gọn đi kèm NGAY TRONG CÙNG
        CÂU, không được để thuật ngữ đứng một mình không giải thích.
      + DIỆN ÁP DỤNG BAO GỒM CẢ TỪ VIẾT TẮT/TÊN CƠ QUAN VIẾT TẮT (ví dụ:
        "UBND", "HĐND", "UBMTTQ", "BHXH", "BHYT"...) - đây KHÔNG phải ngoại
        lệ, phải viết ra tên đầy đủ ngay lần đầu xuất hiện trong đoạn đó,
        cùng nguyên tắc như một thuật ngữ chuyên ngành bình thường.
      + Cách giải thích: chèn cụm giải thích ngắn ngay sau thuật ngữ, có thể
        đặt trong dấu ngoặc đơn hoặc nối bằng dấu phẩy/cụm từ giải nghĩa tự
        nhiên - miễn là người không có chuyên môn đọc vẫn hiểu được nghĩa mà
        không cần tra cứu thêm.
      + Ví dụ:
          Sai: "Sở chủ trì xây dựng đề án sáp nhập các đơn vị sự nghiệp."
          Đúng: "Sở đứng ra tổ chức chính (chủ trì) xây dựng kế hoạch chi tiết
          (đề án) để gộp (sáp nhập) các đơn vị sự nghiệp lại với nhau."
          Sai: "UBND giao Sở Nội vụ thẩm định hồ sơ theo quy trình rút gọn."
          Đúng: "UBND (Ủy ban nhân dân) giao Sở Nội vụ kiểm tra, xét duyệt
          (thẩm định) hồ sơ theo quy trình đơn giản, nhanh hơn bình thường
          (quy trình rút gọn)."
      + Quy tắc này KHÔNG áp dụng cho đoạn thuộc tầng "chuyên sâu", hoặc đoạn
        tầng "nền" khi style tổng thể là "chuyen_sau" - ở các đoạn đó thuật
        ngữ chuyên ngành và từ viết tắt được dùng tự nhiên, không cần giải
        thích lại.
      + LƯU Ý QUAN TRỌNG: "không có chuyên môn" ở đây là góc nhìn của NGƯỜI
        ĐỌC PHỔ THÔNG, không phải góc nhìn của người soạn văn bản hành chính.
        Rất nhiều từ NGHE có vẻ thông dụng trong văn bản nhà nước (ví dụ:
        "quy hoạch tổng thể", "xã hội hóa", "tinh giản biên chế", "dự án đầu
        tư công", "tài sản công", "đề án", "sáp nhập", "phân cấp", "thẩm
        định", "UBND", "HĐND") VẪN PHẢI giải thích ở tầng này - KHÔNG được
        coi là "ai cũng biết rồi nên không cần giải thích". Chỉ được bỏ qua
        giải thích với các từ thuộc vốn từ phổ thông hàng ngày (ví dụ: "báo
        cáo", "kế hoạch", "yêu cầu", "thực hiện").
      + Trước khi viết xong đoạn thuộc tầng này, hãy tự hỏi: "nếu một người
        chưa từng làm việc trong cơ quan nhà nước đọc câu này, họ có hiểu hết
        từng cụm từ VÀ từng từ viết tắt không?" - nếu có bất kỳ cụm hoặc từ
        viết tắt nào còn nghi ngờ, PHẢI thêm giải thích.

    - TÍNH BAO QUÁT:
      + Bản tóm tắt phải phản ánh đầy đủ các nhóm nội dung chính của văn bản.
      + Nếu văn bản gồm nhiều mục thì cần bao quát tất cả các mục quan trọng theo đúng thứ tự.
      + Không được chỉ tóm tắt phần mở đầu hoặc mục đích ban hành rồi kết thúc.
      + Ưu tiên sự đầy đủ và bao quát hơn là rút ngắn tối đa.
    TRƯỚC KHI TRẢ VỀ, tự kiểm tra lại bài viết theo 2 việc sau, rồi mới trả lời:
    1. Nếu phát hiện bất kỳ dòng nào bắt đầu bằng số thứ tự, ký hiệu đánh số,
       hoặc tiêu đề mục tách riêng - PHẢI viết lại đoạn đó thành câu văn xuôi
       liền mạch.
    2. Rà lại TỪNG đoạn ứng với tầng "trung bình" hoặc tầng "nền" (ở style
       "khong_chuyen_mon"/"binh_thuong") - LIỆT KÊ RA TRONG ĐẦU tất cả các
       cụm từ mang tính hành chính/pháp lý/chuyên ngành VÀ tất cả các từ viết
       tắt (UBND, HĐND, BHXH, BHYT...) xuất hiện trong đoạn đó (kể cả các cụm
       nghe quen thuộc như "quy hoạch tổng thể", "xã hội hóa", "tinh giản
       biên chế"...), sau đó kiểm tra từng cụm/từ viết tắt đã có giải thích
       đi kèm trong câu chưa. Cụm/từ nào còn thiếu, PHẢI bổ sung giải thích
       ngắn gọn trước khi trả về.
    Chỉ trả về bản đã kiểm tra lại theo cả 2 việc trên, không trả về bản nháp.
    {checklist_viet_tat}
    """.strip()

    return prompt


async def tom_tat_hanh_chinh_cho_persona(persona, ket_qua_extract, ket_qua_khop_persona, client, semaphore,
                                         model_name=OSS_MODEL_NAME):
    danh_sach_muc = ket_qua_extract.get("danh_sach_muc", [])

    danh_sach_muc_voi_tang, style = gan_tang_do_sau_va_style(
        persona.get("id"), danh_sach_muc, ket_qua_khop_persona
    )

    so_muc_chuyen_sau = sum(1 for m in danh_sach_muc_voi_tang if m["tang_do_sau"] == TANG_CHUYEN_SAU)
    so_muc_trung_binh = sum(1 for m in danh_sach_muc_voi_tang if m["tang_do_sau"] == TANG_TRUNG_BINH)

    if style == "binh_thuong":
        cac_batch_muc = _chia_muc_theo_token(danh_sach_muc_voi_tang, style)
    else:
        cac_batch_muc = [
            [muc] for muc in danh_sach_muc_voi_tang
            if muc.get("heading") is not None or muc.get("doan_van")
        ]

    async def _goi_1_batch(batch_muc, idx_batch):
        prompt = build_hanh_chinh_prompt(persona, ket_qua_extract, batch_muc, style)
        so_ky_tu = len(prompt)
        so_token_uoc_luong = uoc_luong_so_token(prompt)
        print(
            f"[DEBUG] {persona.get('id')} — file {ket_qua_extract.get('file')} — "
            f"batch {idx_batch}/{len(cac_batch_muc)} ({len(batch_muc)} mục): "
            f"prompt {so_ky_tu} ký tự (~{so_token_uoc_luong} token ước lượng)"
        )

        async def _goi(max_tokens):
            async def _call():
                return await client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"temperature": 0.0, "max_output_tokens": max_tokens},
                )

            async with semaphore:
                try:
                    return await retry_generate_async(_call)
                except Exception as loi:
                    print(
                        f"[DEBUG-LỖI] {persona.get('id')} — file {ket_qua_extract.get('file')} — "
                        f"batch {idx_batch}/{len(cac_batch_muc)}: gọi LLM thất bại sau hết retry ({loi}). "
                        f"prompt {so_ky_tu} ký tự (~{so_token_uoc_luong} token ước lượng)."
                    )
                    raise

        max_tokens_1 = _tinh_max_output_token_an_toan(so_token_uoc_luong, HANH_CHINH_MAX_OUTPUT_TOKENS)
        response = await _goi(max_tokens_1)
        bi_cat_cut = getattr(response, "finish_reason", None) == "length"
        if bi_cat_cut:
            max_tokens_2 = _tinh_max_output_token_an_toan(so_token_uoc_luong, HANH_CHINH_MAX_OUTPUT_TOKENS_MO_RONG)
            print(
                f"[DEBUG] {persona.get('id')} — file {ket_qua_extract.get('file')} — "
                f"batch {idx_batch}/{len(cac_batch_muc)}: output bị cắt cụt ở {max_tokens_1} token, "
                f"thử lại với {max_tokens_2} token."
            )
            response = await _goi(max_tokens_2)
            bi_cat_cut = getattr(response, "finish_reason", None) == "length"
            if bi_cat_cut:
                print(
                    f"[DEBUG-LỖI] {persona.get('id')} — file {ket_qua_extract.get('file')} — "
                    f"batch {idx_batch}/{len(cac_batch_muc)}: VẪN bị cắt cụt sau khi mở rộng lên "
                    f"{max_tokens_2} token (prompt đã chiếm ~{so_token_uoc_luong}/{OSS_CONTEXT_LIMIT} "
                    f"token) — cần soát tay, có thể phải giảm NGUONG_TOKEN_MOI_BATCH_MUC."
                )

        doan_tho = response.text.strip()
        if _batch_can_giai_thich(batch_muc, style):
            doan_tho = _bo_sung_giai_thich_tu_viet_tat(doan_tho)
        return doan_tho, bi_cat_cut

    ket_qua_batch_goi = await asyncio.gather(
        *[_goi_1_batch(batch, i) for i, batch in enumerate(cac_batch_muc, 1)]
    )
    cac_doan = [doan for doan, _ in ket_qua_batch_goi]
    cac_batch_bi_cat_cut = [i for i, (_, cat) in enumerate(ket_qua_batch_goi, 1) if cat]
    summary = "\n\n".join(doan for doan in cac_doan if doan.strip())

    danh_sach_muc_luu = [
        {
            "heading": m.get("heading"),
            "doan_van": m.get("doan_van", []),
            "tang_do_sau": m["tang_do_sau"],
        }
        for m in danh_sach_muc_voi_tang
    ]

    return {
        "id": persona.get("id"),
        "file": ket_qua_extract.get("file"),
        "style": style,
        "summary": summary,
        "so_muc_chuyen_sau": so_muc_chuyen_sau,
        "so_muc_trung_binh": so_muc_trung_binh,
        "so_muc_tong": len(danh_sach_muc_voi_tang),
        "so_batch": len(cac_batch_muc),
        "cac_batch_bi_cat_cut": cac_batch_bi_cat_cut,
        "danh_sach_muc_voi_tang": danh_sach_muc_luu,
    }

if __name__ == "__main__":
    import argparse
    from pipeline.hanhchinh.hanh_chinh_extract import xu_ly_1_file
    from pipeline.hanhchinh.hanh_chinh_persona_match_gpt import (
        chay_khop_persona_cho_van_ban,
    )

    parser = argparse.ArgumentParser(description="Tom tat hanh chinh ca nhan hoa cho 1 persona")
    parser.add_argument("--file", required=True, help="duong dan file docx van ban hanh chinh")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", help="id cua persona, vi du NN0001")
    group.add_argument("--so-luong", type=int, help="chay tu persona dau tien den persona thu n")
    group.add_argument("--tu-id", help="chạy từ persona này (vd NN0018), dùng kèm --den-id")
    parser.add_argument("--den-id", help="id persona kết thúc, dùng kèm --tu-id (vd NN0026)")
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        help="ten bien the persona, neu co se ghi vao thu muc con rieng de tranh de len du lieu persona day du truong"
    )
    args = parser.parse_args()

    duong_dan_file = Path(args.file)
    if not duong_dan_file.exists():
        duong_dan_file = ROOT_DIR / "data" / "hanh_chinh" / duong_dan_file
    if not duong_dan_file.exists():
        raise SystemExit(f"Không tìm thấy file: {duong_dan_file}")

    EXTRACT_CACHE_DIR = ROOT_DIR / "output" / "hanh_chinh" / "extract"
    MATCH_CACHE_DIR = ROOT_DIR / "output" / "hanh_chinh" / "persona_match"
    SUMMARY_DIR = ROOT_DIR / "output" / "hanh_chinh" / "summary"
    for d in (EXTRACT_CACHE_DIR, MATCH_CACHE_DIR, SUMMARY_DIR):
        d.mkdir(parents=True, exist_ok=True)

    ten_file_goc = duong_dan_file.stem

    extract_cache_path = EXTRACT_CACHE_DIR / f"{ten_file_goc}.json"
    if extract_cache_path.exists():
        with open(extract_cache_path, encoding="utf-8") as f:
            ket_qua_extract = json.load(f)
        print(f"Đã đọc kết quả trích xuất từ cache: {extract_cache_path}")
    else:
        print(f"Đang trích xuất văn bản từ: {duong_dan_file}")
        ket_qua_extract = xu_ly_1_file(str(duong_dan_file))
        with open(extract_cache_path, "w", encoding="utf-8") as f:
            json.dump(ket_qua_extract, f, ensure_ascii=False, indent=2)

    ten_file_persona = f"state_profiles_{args.variant}.json" if args.variant else "state_profiles_nt_nn_tc_kn_cd_ch.json"
    duong_dan_persona = ROOT_DIR / "data" / "profile" / ten_file_persona
    with open(duong_dan_persona, encoding="utf-8") as f:
        personas = json.load(f)
    if args.id:
        personas_can_chay = [p for p in personas if p.get("id") == args.id]
        if not personas_can_chay:
            raise SystemExit(
                f"Không tìm thấy persona có id = {args.id} trong {duong_dan_persona}"
            )
    elif args.tu_id:
        so_tu = int(re.sub(r"\D", "", args.tu_id))
        so_den = int(re.sub(r"\D", "", args.den_id)) if args.den_id else so_tu
        personas_can_chay = [
            p for p in personas
            if so_tu <= int(re.sub(r"\D", "", p.get("id", "0"))) <= so_den
        ]
        if not personas_can_chay:
            raise SystemExit(
                f"Không tìm thấy persona nào trong khoảng {args.tu_id} - {args.den_id or args.tu_id}"
            )
    else:
        personas_can_chay = personas[:args.so_luong]

    if args.variant:
        out_dir = SUMMARY_DIR / args.variant / ten_file_goc
    else:
        out_dir = SUMMARY_DIR / ten_file_goc
    out_dir.mkdir(parents=True, exist_ok=True)

    async def xu_ly_mot_persona(client, semaphore, persona, ket_qua_extract, ket_qua_khop_persona, i, tong):
        out_path_json = out_dir / f"{persona['id']}.json"
        out_path_md = out_dir / f"{persona['id']}.md"

        if out_path_json.exists():
            print(f"[{i}/{tong}] {persona['id']} đã tồn tại -> bỏ qua")
            return

        print(f"\n[{i}/{tong}] Bắt đầu xử lý {persona['id']}...")

        ket_qua = await tom_tat_hanh_chinh_cho_persona(
            persona,
            ket_qua_extract,
            ket_qua_khop_persona,
            client,
            semaphore,
        )

        with open(out_path_json, "w", encoding="utf-8") as f:
            json.dump(ket_qua, f, ensure_ascii=False, indent=2)

        with open(out_path_md, "w", encoding="utf-8") as f:
            f.write(ket_qua["summary"])

        print(f"Style: {ket_qua['style']}")
        print(
            f"Chuyên sâu: {ket_qua['so_muc_chuyen_sau']}, "
            f"TB: {ket_qua['so_muc_trung_binh']}"
        )
        print(f"Đã ghi: {out_path_json}")

    async def chay():
        client = tao_oss_client_async()
        semaphore = asyncio.Semaphore(OSS_MAX_CONCURRENCY_SUMMARY)

        match_cache_path = MATCH_CACHE_DIR / f"{ten_file_goc}.json"
        if match_cache_path.exists():
            with open(match_cache_path, encoding="utf-8") as f:
                ket_qua_khop_persona = json.load(f)
            print(f"Đã đọc kết quả khớp persona từ cache: {match_cache_path}")
        else:
            print("Đang gọi LLM khớp persona theo ngành...")
            ket_qua_khop_persona = await chay_khop_persona_cho_van_ban(client, semaphore, ket_qua_extract)
            with open(match_cache_path, "w", encoding="utf-8") as f:
                json.dump(ket_qua_khop_persona, f, ensure_ascii=False, indent=2)

        tong = len(personas_can_chay)
        tasks = [
            xu_ly_mot_persona(client, semaphore, persona, ket_qua_extract, ket_qua_khop_persona, i, tong)
            for i, persona in enumerate(personas_can_chay, start=1)
        ]
        await asyncio.gather(*tasks)

    asyncio.run(chay())