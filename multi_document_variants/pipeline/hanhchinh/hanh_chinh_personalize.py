import os
import re
import json
from pathlib import Path

from pipeline.utils import retry_generate, SUMMARY_MODEL_NAME
# ==== BƯỚC 1: XÁC ĐỊNH TẦNG ĐỘ SÂU CHO TỪNG MỤC + STYLE TOÀN BÀI ====

TANG_CHUYEN_SAU = 0
TANG_TRUNG_BINH = 1
TANG_NEN = 2

DO_TIN_CAY_SANG_TANG = {"cao": TANG_CHUYEN_SAU, "trung bình": TANG_TRUNG_BINH}


def _chi_so_da_khop_persona(persona_id, ket_qua_khop_persona):
    ket_qua = {}
    for entry in ket_qua_khop_persona:
        if persona_id in entry.get("danh_sach_persona_id_khop", []):
            chi_so_goc = entry.get("chi_so_doi_tuong_goc")
            if chi_so_goc is not None:
                ket_qua[chi_so_goc] = entry.get("do_tin_cay", "thap")
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

def persona_co_khop_van_ban(persona_id, ket_qua_khop_persona):
    """
    Kiểm tra persona này có xuất hiện trong danh_sach_persona_id_khop của
    BẤT KỲ đối tượng thi hành nào trong văn bản hay không. Dùng để chặn
    sớm trường hợp chạy nhầm persona không liên quan gì tới văn bản.
    """
    for entry in ket_qua_khop_persona:
        if persona_id in entry.get("danh_sach_persona_id_khop", []):
            return True
    return False

# ==== BƯỚC 2: TEXT HƯỚNG DẪN THEO TẦNG ĐỘ SÂU VÀ THEO STYLE ====

MUC_DO_THEO_TANG = {
    TANG_CHUYEN_SAU: (
        "Đây là phần LIÊN QUAN TRỰC TIẾP nhất tới công việc/chuyên môn của "
        "người đọc (khớp đúng, cụ thể). Tóm tắt ĐẦY ĐỦ, không bỏ sót ý quan "
        "trọng nào trong nội dung gốc. BẮT BUỘC Giữ nguyên nhiệm vụ cụ thể, số liệu, "
        "mốc thời gian, đơn vị chủ trì/phối hợp. Người đọc CÓ chuyên "
        "môn đúng phần này: dùng thuật ngữ hành chính, pháp lý, chuyên ngành "
        "một cách tự nhiên, KHÔNG giải thích lại các khái niệm cơ bản trong "
        "ngành đó - coi như người đọc đã biết."
    ),
    TANG_TRUNG_BINH: (
        "Đây là phần liên quan nhưng ở mức CHUNG (áp dụng rộng cho nhiều "
        "ngành, không riêng chuyên môn của người đọc). Tóm tắt đủ ý chính, "
        "không cần đi sâu chi tiết như phần liên quan trực tiếp. Người đọc "
        "KHÔNG CÓ chuyên môn đúng phần này: dùng ngôn ngữ PHỔ THÔNG, dễ "
        "hiểu; nếu buộc phải dùng thuật ngữ hành chính/pháp lý thì giải "
        "thích ngắn gọn ngay trong câu."
    ),
    TANG_NEN: (
        "Đây là phần NỀN, không liên quan trực tiếp tới công việc của người "
        "đọc, chỉ giữ lại để có bối cảnh chung của văn bản. Tóm tắt RẤT NGẮN "
        "GỌN, chỉ nêu khái quát trong 1 câu, không đi vào chi tiết, dùng "
        "ngôn ngữ phổ thông đơn giản, không dùng thuật ngữ chuyên ngành. "
        "QUY TẮC BẮT BUỘC: DÙ nội dung gốc của mục này DÀI đến đâu, có "
        "nhiều nhiệm vụ/số liệu/mốc thời gian/tên đơn vị cụ thể đến đâu, "
        "TUYỆT ĐỐI KHÔNG được viết dài hơn 1 câu duy nhất cho mục này - "
        "nội dung dài của nguồn KHÔNG PHẢI lý do để viết dài hơn giới hạn."
    ),
}


def _dem_so_cau(text):
    """Đếm số câu trong văn bản, tách theo dấu chấm/chấm than/chấm hỏi,
    bỏ qua các phần rỗng (dùng để hậu kiểm độ dài khi toàn bộ mục là tầng
    nền - lúc đó cả bản tóm tắt PHẢI rất ngắn)."""
    cac_cau = re.split(r"[.!?]+", text)
    return len([c for c in cac_cau if c.strip()])


SO_CAU_TOI_DA_KHI_TOAN_NEN = 3
SO_LAN_THU_TOI_DA_KHI_TOAN_NEN = 2


# ==== BƯỚC 3: DỰNG PROMPT ====

def _dinh_dang_danh_sach_muc(danh_sach_muc):
    ds = ""
    for i, muc in enumerate(danh_sach_muc, 1):
        if muc.get("heading") is None and not muc.get("doan_van"):
            continue
        noi_dung = "\n   ".join(muc.get("doan_van", []))
        tang = muc.get("tang_do_sau", TANG_NEN)
        ds += (
            f"\n{i}. Mục: \"{muc.get('heading') or '(không có tiêu đề riêng)'}\"\n"
            f"   Nội dung: {noi_dung}\n"
            f"   Yêu cầu cho mục này: {MUC_DO_THEO_TANG[tang]}\n"
        )
    return ds


def build_hanh_chinh_prompt(persona, ket_qua_extract, danh_sach_muc_voi_tang):
    loai_van_ban = ket_qua_extract.get("loai_van_ban", "")
    danh_sach_muc_text = _dinh_dang_danh_sach_muc(danh_sach_muc_voi_tang)

    prompt = f"""Bạn đang tóm tắt cá nhân hóa 1 văn bản hành chính (loại: {loai_van_ban})
    cho một cán bộ có hồ sơ công vụ sau:

    - Ngành/lĩnh vực: {persona.get('nganh_to')} - {persona.get('nganh_nho')}
    - Đơn vị công tác: {persona.get('to_chuc')}
    - Mô tả chung: {persona.get('mo_ta_chung')}

    Dưới đây là toàn bộ nội dung văn bản, đã chia theo mục, GIỮ NGUYÊN THỨ TỰ như
    văn bản gốc. Mỗi mục có ghi rõ yêu cầu độ chi tiết VÀ văn phong riêng - PHẢI
    tuân thủ đúng yêu cầu đó cho TỪNG mục, không viết đều tay như nhau cho tất cả
    các mục kể cả về độ dài lẫn cách dùng từ ngữ:
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
      + Quy tắc này ĐÚNG NGUYÊN VẸN với mọi văn bản, không được nới lỏng chỉ vì
        văn bản có nhiều mục hoặc mục dài - càng nhiều mục càng phải viết liền
        mạch bằng câu dẫn chuyển ý, không phải bằng cách đánh số.
    - Các mục có yêu cầu "tóm tắt RẤT NGẮN GỌN" (phần nền) thực sự phải ngắn -
      không viết dài hơn 1-2 câu, không cố kéo dài giả tạo.
    - KHÔNG tự suy luận, đánh giá hoặc thêm nhận định không có trong văn bản gốc.
    - KHÔNG chèn bất kỳ câu/cụm chú thích nào về quá trình viết bài (ví dụ:
      "(mục này được tóm gọn vì...)"). Bài trả về chỉ là văn bản tóm tắt tự nhiên.
    - Chỉ trả về nội dung văn bản, không thêm lời dẫn kiểu "Dưới đây là...".

    TRƯỚC KHI TRẢ VỀ, tự kiểm tra lại bài viết: nếu phát hiện bất kỳ dòng nào bắt
    đầu bằng số thứ tự, ký hiệu đánh số, hoặc tiêu đề mục tách riêng - PHẢI viết
    lại đoạn đó thành câu văn xuôi liền mạch trước khi trả về câu trả lời cuối
    cùng. Chỉ trả về bản đã kiểm tra lại, không trả về bản nháp.
    """.strip()

    return prompt


# ==== BƯỚC 4: HÀM CHẠY CHÍNH CHO 1 PERSONA ====

def tom_tat_hanh_chinh_cho_persona(persona, ket_qua_extract, ket_qua_khop_persona, client,
                                   model_name=SUMMARY_MODEL_NAME):
    danh_sach_muc = ket_qua_extract.get("danh_sach_muc", [])

    danh_sach_muc_voi_tang, style = gan_tang_do_sau_va_style(
        persona.get("id"), danh_sach_muc, ket_qua_khop_persona
    )

    so_muc_chuyen_sau = sum(1 for m in danh_sach_muc_voi_tang if m["tang_do_sau"] == TANG_CHUYEN_SAU)
    so_muc_trung_binh = sum(1 for m in danh_sach_muc_voi_tang if m["tang_do_sau"] == TANG_TRUNG_BINH)
    toan_bo_la_nen = (so_muc_chuyen_sau == 0 and so_muc_trung_binh == 0)

    prompt = build_hanh_chinh_prompt(persona, ket_qua_extract, danh_sach_muc_voi_tang)

    def _call(prompt_hien_tai):
        def _goi():
            return client.models.generate_content(
                model=model_name,
                contents=prompt_hien_tai,
                config={"temperature": 0.0},
            )
        return retry_generate(_goi)

    response = _call(prompt)
    summary = response.text.strip()

    if toan_bo_la_nen:
        so_lan_thu = 1
        prompt_hien_tai = prompt
        while _dem_so_cau(summary) > SO_CAU_TOI_DA_KHI_TOAN_NEN and so_lan_thu < SO_LAN_THU_TOI_DA_KHI_TOAN_NEN:
            print(f"CẢNH BÁO: persona {persona.get('id')} - toàn bộ mục là tầng nền "
                  f"nhưng bản tóm tắt có {_dem_so_cau(summary)} câu (giới hạn "
                  f"{SO_CAU_TOI_DA_KHI_TOAN_NEN}) - thử lại lần {so_lan_thu + 1}...")
            prompt_hien_tai = prompt + (
                f"\n\nLƯU Ý QUAN TRỌNG: bản trả lời trước của bạn quá dài "
                f"({_dem_so_cau(summary)} câu). Toàn bộ nội dung văn bản này đều "
                f"thuộc tầng 'nền' đối với người đọc - PHẢI nén xuống TỐI ĐA "
                f"{SO_CAU_TOI_DA_KHI_TOAN_NEN} câu, chỉ nêu khái quát văn bản nói "
                f"về việc gì, không liệt kê nhiệm vụ/đơn vị/mốc thời gian cụ thể."
            )
            response = _call(prompt_hien_tai)
            summary = response.text.strip()
            so_lan_thu += 1

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
        "danh_sach_muc_voi_tang": danh_sach_muc_luu,
    }

if __name__ == "__main__":
    import argparse
    from google import genai
    from pipeline.hanhchinh.hanh_chinh_extract import xu_ly_1_file
    from pipeline.hanhchinh.hanh_chinh_persona_match import (
        chay_khop_persona_cho_van_ban, PROFILE_PATH, ROOT_DIR,
    )

    API_KEY = os.getenv("API_KEY")

    parser = argparse.ArgumentParser(description="Tom tat hanh chinh ca nhan hoa cho 1 persona")
    parser.add_argument("--file", required=True, help="duong dan file docx van ban hanh chinh")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", help="id cua persona, vi du NN0001")
    group.add_argument("--so-luong", type=int, help="chay tu persona dau tien den persona thu n")
    args = parser.parse_args()

    duong_dan_file = Path(args.file)
    if not duong_dan_file.exists():
        duong_dan_file = ROOT_DIR / "data" / "hanh_chinh" / duong_dan_file
    if not duong_dan_file.exists():
        raise SystemExit(f"Không tìm thấy file: {duong_dan_file}")

    client = genai.Client(api_key=API_KEY)

    EXTRACT_CACHE_DIR = ROOT_DIR / "output" / "hanh_chinh" / "extract"
    MATCH_CACHE_DIR = ROOT_DIR / "output" / "hanh_chinh" / "persona_match"
    SUMMARY_DIR = ROOT_DIR / "output" / "hanh_chinh" / "summary"
    for d in (EXTRACT_CACHE_DIR, MATCH_CACHE_DIR, SUMMARY_DIR):
        d.mkdir(parents=True, exist_ok=True)

    ten_file_goc = duong_dan_file.stem

    # bước 1: trích xuất - dùng cache nếu đã chạy văn bản này trước đó,
    # để không phải đọc lại docx mỗi lần đổi persona
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

    # bước 2: khớp persona theo ngành - có gọi LLM nên cũng cache lại,
    # để đổi persona khác trên CÙNG văn bản không phải gọi LLM lại
    match_cache_path = MATCH_CACHE_DIR / f"{ten_file_goc}.json"
    if match_cache_path.exists():
        with open(match_cache_path, encoding="utf-8") as f:
            ket_qua_khop_persona = json.load(f)
        print(f"Đã đọc kết quả khớp persona từ cache: {match_cache_path}")
    else:
        print("Đang gọi LLM khớp persona theo ngành...")
        ket_qua_khop_persona = chay_khop_persona_cho_van_ban(client, ket_qua_extract)
        with open(match_cache_path, "w", encoding="utf-8") as f:
            json.dump(ket_qua_khop_persona, f, ensure_ascii=False, indent=2)

    # bước 3: chặn sớm nếu persona không thực sự khớp văn bản này
    if not persona_co_khop_van_ban(args.id, ket_qua_khop_persona):
        print(f"\nCẢNH BÁO: persona {args.id} KHÔNG nằm trong danh_sach_persona_id_khop")
        print(f"của bất kỳ mục nào trong văn bản này (xem chi tiết tại {match_cache_path}).")
        print("Nếu vẫn chạy, toàn bộ văn bản sẽ bị coi là 'phần nền', bản tóm tắt sẽ")
        print("rất ngắn gọn cho mọi mục - khả năng cao đây không phải ý bạn muốn.")
        xac_nhan = input("Vẫn tiếp tục chạy? (y/n): ").strip().lower()
        if xac_nhan != "y":
            raise SystemExit("Đã hủy.")

    # bước 4: load persona theo id
    with open(PROFILE_PATH, encoding="utf-8") as f:
        personas = json.load(f)
    if args.id:
        personas_can_chay = [p for p in personas if p.get("id") == args.id]
        if not personas_can_chay:
            raise SystemExit(
                f"Không tìm thấy persona có id = {args.id} trong {PROFILE_PATH}"
            )
    else:
        personas_can_chay = personas[:args.so_luong]

    out_dir = SUMMARY_DIR / ten_file_goc
    out_dir.mkdir(parents=True, exist_ok=True)

    tong = len(personas_can_chay)

    for i, persona in enumerate(personas_can_chay, start=1):

        out_path_json = out_dir / f"{persona['id']}.json"
        out_path_md = out_dir / f"{persona['id']}.md"

        # đã chạy rồi thì bỏ qua
        if out_path_json.exists():
            print(f"[{i}/{tong}] {persona['id']} đã tồn tại -> bỏ qua")
            continue

        print(f"\n[{i}/{tong}] Bắt đầu xử lý {persona['id']}...")

        ket_qua = tom_tat_hanh_chinh_cho_persona(
            persona,
            ket_qua_extract,
            ket_qua_khop_persona,
            client,
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