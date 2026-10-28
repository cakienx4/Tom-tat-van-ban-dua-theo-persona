import json
import re
import time
import asyncio
from pathlib import Path

from pipeline.utils import (
    retry_generate_async, OSS_MODEL_NAME, tao_oss_client_async,
    OSS_MAX_CONCURRENCY_SUMMARY, uoc_luong_so_token,
)
ROOT_DIR = Path(__file__).resolve().parents[2]

TIEU_CHI = [
    "chon_loc_phu_hop",
    "nhat_quan",
    "trinh_bay_phu_hop",
    "bo_cuc_uu_tien",
    "giong_dieu_phu_hop",
    "thai_do_dung_dan",
]

TANG_TEN = {0: "chuyên sâu", 1: "trung bình", 2: "nền"}
NGUONG_TI_LE_PASS_BATCH = 0.8

EVAL_MAX_OUTPUT_TOKENS = 4096
EVAL_MAX_OUTPUT_TOKENS_MO_RONG = 8000
NGUONG_TOKEN_MOI_BATCH_MUC_CHAM = 2000



def loc_muc_hop_le(danh_sach_muc):
    ket_qua = []
    for m in danh_sach_muc:
        if m.get("heading") is None and not m.get("doan_van"):
            continue
        ket_qua.append(m)
    return ket_qua



def dinh_dang_danh_sach_muc(danh_sach_muc_loc):
    ds = ""
    for i, muc in enumerate(danh_sach_muc_loc, 1):
        noi_dung = "\n   ".join(muc.get("doan_van", []))
        tang = muc.get("tang_do_sau", 2)
        ds += (
            f"\n[MỤC {i}] (tầng độ sâu yêu cầu: {TANG_TEN.get(tang, 'nền')})\n"
            f"Tiêu đề: \"{muc.get('heading') or '(không có tiêu đề riêng)'}\"\n"
            f"Nội dung gốc: {noi_dung}\n"
        )
    return ds

def _dinh_dang_headings_only(danh_sach_muc_loc):
    ds = ""
    for i, muc in enumerate(danh_sach_muc_loc, 1):
        tang = muc.get("tang_do_sau", 2)
        ds += f"[MỤC {i}] (tầng: {TANG_TEN.get(tang, 'nền')}) — \"{muc.get('heading') or '(không có tiêu đề riêng)'}\"\n"
    return ds


def _uoc_luong_token_mot_muc(muc):
    return uoc_luong_so_token(dinh_dang_danh_sach_muc([muc]))


def _chia_muc_theo_token_cham(danh_sach_muc_loc):
    batches = []
    batch_hien_tai = []
    token_hien_tai = 0

    for muc in danh_sach_muc_loc:
        token_muc = _uoc_luong_token_mot_muc(muc)
        if batch_hien_tai and token_hien_tai + token_muc > NGUONG_TOKEN_MOI_BATCH_MUC_CHAM:
            batches.append(batch_hien_tai)
            batch_hien_tai = []
            token_hien_tai = 0
        batch_hien_tai.append(muc)
        token_hien_tai += token_muc

    if batch_hien_tai:
        batches.append(batch_hien_tai)

    return batches


MAU_DANH_SO_MUC = re.compile(
    r"(^|\n)\s*(mục\s*\d+[:.]|(\(?\d+[.)]\s){1}|[IVX]+[.)]\s)",
    re.IGNORECASE,
)


def hau_kiem_dinh_dang(summary):
    ly_do = []
    if MAU_DANH_SO_MUC.search(summary):
        ly_do.append(
            "Phát hiện mẫu đánh số/tiêu đề mục còn sót trong văn bản "
            "(regex khớp dạng 'Mục N:', '1.', 'I.' ở đầu dòng)."
        )
    return ly_do


_TU_KHOA_LOAI_TRU_HAU_KIEM = {
    "binh_thuong", "khong_chuyen_mon", "chuyen_sau",
    "chuyên sâu", "trung bình", "nền",
}


def _trich_cac_doan_trich_dan(text):
    ket_qua = []
    ket_qua.extend(re.findall(r'"([^"]*)"', text))
    ket_qua.extend(re.findall(r'“([^”]*)”', text))

    ket_qua_loc = []
    for t in ket_qua:
        t_sach = t.strip()
        if len(t_sach) < 8:
            continue
        if _chuan_hoa(t_sach) in _TU_KHOA_LOAI_TRU_HAU_KIEM:
            continue
        ket_qua_loc.append(t_sach)
    return ket_qua_loc


def _chuan_hoa(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


_MAU_SO_HIEU_VAN_BAN = re.compile(
    r"\d{1,6}(?:/\d{2,4})?[/-][A-ZĐƯ]{1,4}[A-Za-zĐƯđư]{0,8}(?:[/-][A-ZĐƯ][A-Za-zĐƯđư]{0,8})*"
)
_MANH_SO_HIEU_VAN_BAN = re.compile(
    r"\b(?:TTg|TCCV|NQ[/-](?:TW|HĐND|CP)|NQ-HĐND|NĐ[-/]CP|QĐ[-/](?:UBND|TTg)|KH[-/][A-ZĐƯ]{2,10}|CV[-/][A-ZĐƯ]{2,10})\b"
)
_TU_KHOA_THIEU_CAN_CU = (
    "không đề cập", "không nêu", "không giữ", "không xuất hiện", "thiếu",
    "không có", "không cung cấp", "không nhắc", "không được đề cập",
)


def _fail_vi_doi_hoi_so_hieu_van_ban(tc, ly_do):
    if tc not in ("bo_cuc_chi_tiet_theo_tang", "bo_cuc_uu_tien_thu_tu"):
        return False
    if not _MAU_SO_HIEU_VAN_BAN.search(ly_do):
        return False
    ly_do_thuong = ly_do.lower()
    return any(tu_khoa in ly_do_thuong for tu_khoa in _TU_KHOA_THIEU_CAN_CU)


def _fail_giong_dieu_vi_so_hieu_van_ban(tc, ly_do):
    if tc != "giong_dieu_phu_hop":
        return False
    return bool(_MAU_SO_HIEU_VAN_BAN.search(ly_do)) or bool(_MANH_SO_HIEU_VAN_BAN.search(ly_do))

_MAU_TU_VIET_TAT_HOP_LE = re.compile(r"^[A-ZĐƯ0-9](?:[A-ZĐƯ0-9/\-\.&]){1,14}$")

def _fail_giong_dieu_vi_khong_phai_tu_viet_tat(tc, ly_do):
    if tc != "giong_dieu_phu_hop":
        return False
    cac_trich = _trich_cac_doan_trich_dan(ly_do)
    if not cac_trich:
        return False
    return not any(_MAU_TU_VIET_TAT_HOP_LE.match(t.strip()) for t in cac_trich)

def hau_kiem_va_sua_batch(nhan_batch, ket_qua_batch, summary):
    summary_chuan = _chuan_hoa(summary)
    canh_bao = []
    ket_qua_da_sua = {}

    for tc, ket in ket_qua_batch.items():
        if not isinstance(ket, dict) or ket.get("verdict") != "fail":
            ket_qua_da_sua[tc] = ket
            continue

        ly_do = ket.get("ly_do", "")

        if _fail_vi_doi_hoi_so_hieu_van_ban(tc, ly_do):
            ket_qua_da_sua[tc] = {
                "verdict": "pass",
                "ly_do": (
                    f"[TỰ ĐỘNG SỬA] Verdict gốc là fail nhưng lý do lại đòi giữ số hiệu/ngày "
                    f"ban hành văn bản viện dẫn - TRÁI với chính quy tắc chấm tiêu chí này (đã "
                    f"ghi rõ: lược bỏ số hiệu/ngày ban hành là ĐÚNG, không fail vì thiếu). Coi "
                    f"là pass, cần soát tay. Lý do gốc: {ly_do}"
                ),
            }
            canh_bao.append(
                f"[{nhan_batch}/{tc}] TỰ ĐỘNG SỬA verdict fail→pass do judge tự mâu thuẫn "
                f"(đòi giữ số hiệu/ngày ban hành văn bản viện dẫn dù quy tắc nói KHÔNG cần)."
            )
            continue

        if _fail_giong_dieu_vi_khong_phai_tu_viet_tat(tc, ly_do):
            ket_qua_da_sua[tc] = {
                "verdict": "pass",
                "ly_do": (
                    f"[TỰ ĐỘNG SỬA] Verdict gốc là fail nhưng các cụm trích dẫn làm bằng chứng "
                    f"đều KHÔNG phải từ viết tắt (không khớp dạng chữ hoa liền nhau) - TRÁI với "
                    f"chính phạm vi tiêu chí này (chỉ xét từ viết tắt, xem "
                    f"build_judge_prompt_theo_batch, mục giong_dieu_phu_hop). Coi là pass, cần "
                    f"soát tay. Lý do gốc: {ly_do}"
                ),
            }
            canh_bao.append(
                f"[{nhan_batch}/{tc}] TỰ ĐỘNG SỬA verdict fail→pass do judge fail dựa trên cụm "
                f"từ không phải từ viết tắt (vi phạm phạm vi tiêu chí do chính judge đặt ra)."
            )
            continue

        if _fail_giong_dieu_vi_so_hieu_van_ban(tc, ly_do):
            ket_qua_da_sua[tc] = {
                "verdict": "pass",
                "ly_do": (
                    f"[TỰ ĐỘNG SỬA] Verdict gốc là fail nhưng lý do lại coi số hiệu/tên văn "
                    f"bản viện dẫn là thuật ngữ/từ viết tắt cần giải thích - TRÁI với chính "
                    f"quy tắc chấm tiêu chí này (đã ghi rõ: số hiệu văn bản không thuộc phạm "
                    f"vi tiêu chí, không fail vì lý do đó). Coi là pass, cần soát tay. Lý do "
                    f"gốc: {ly_do}"
                ),
            }
            canh_bao.append(
                f"[{nhan_batch}/{tc}] TỰ ĐỘNG SỬA verdict fail→pass do judge nhầm số hiệu/tên "
                f"văn bản viện dẫn thành thuật ngữ cần giải thích."
            )
            continue

        cac_trich = _trich_cac_doan_trich_dan(ly_do)
        so_bia = 0
        for trich in cac_trich:
            if _chuan_hoa(trich) not in summary_chuan:
                so_bia += 1
                canh_bao.append(
                    f"[{nhan_batch}/{tc}] trích dẫn \"{trich[:60]}...\" KHÔNG có trong bản "
                    f"tóm tắt - có khả năng judge bịa nội dung."
                )

        if cac_trich and so_bia >= len(cac_trich):
            ket_qua_da_sua[tc] = {
                "verdict": "pass",
                "ly_do": (
                    f"[TỰ ĐỘNG SỬA] Verdict gốc là fail nhưng TOÀN BỘ trích dẫn làm bằng chứng "
                    f"đều không tìm thấy trong bản tóm tắt (judge có khả năng bịa nội dung) - "
                    f"coi là pass, cần soát tay. Lý do gốc: {ly_do}"
                ),
            }
            canh_bao.append(
                f"[{nhan_batch}/{tc}] TỰ ĐỘNG SỬA verdict fail→pass do toàn bộ trích dẫn bịa."
            )
        else:
            if not cac_trich:
                canh_bao.append(
                    f"[{nhan_batch}/{tc}] verdict fail nhưng KHÔNG trích dẫn câu cụ thể nào - "
                    f"vi phạm quy tắc trích dẫn bắt buộc, GIỮ NGUYÊN fail (không đủ căn cứ coi "
                    f"là judge bịa), cần soát tay."
                )
            ket_qua_da_sua[tc] = ket

    return ket_qua_da_sua, canh_bao



def build_judge_prompt_tong_the(persona, ket_qua_tom_tat, danh_sach_muc_loc):
    danh_sach_headings = _dinh_dang_headings_only(danh_sach_muc_loc)
    so_muc_hop_le = len(danh_sach_muc_loc)

    ho_so = f"""
Ngành/lĩnh vực: {persona.get('nganh_to', '')} - {persona.get('nganh_nho', '')}
Đơn vị công tác: {persona.get('to_chuc', '')}
Mô tả chung: {persona.get('mo_ta_chung', '')}
Style tổng thể: {ket_qua_tom_tat.get('style')}
""".strip()

    prompt = f"""Giám khảo chấm bản tóm tắt cá nhân hóa văn bản hành chính, theo 3 tiêu chí TỔNG
THỂ. Mỗi tiêu chí trả "verdict": pass/fail kèm "ly_do" (trích dẫn cụ thể từ bản tóm tắt).

HỒ SƠ: {ho_so}

MỤC VĂN BẢN GỐC (chỉ tiêu đề + tầng, đúng thứ tự):
{danh_sach_headings}
Tổng {so_muc_hop_le} mục.

BẢN TÓM TẮT:
\"\"\"
{ket_qua_tom_tat.get('summary')}
\"\"\"

TIÊU CHÍ:

1. nhat_quan: văn phong/xưng hô không mâu thuẫn giữa các đoạn. LƯU Ý: cùng 1 thuật ngữ được
   giải thích ở đoạn này nhưng không giải thích ở đoạn khác là ĐÚNG THIẾT KẾ (do phân tầng độ
   sâu khác nhau - xem tầng ghi kèm mỗi mục), KHÔNG fail vì lý do đó. Chỉ fail khi 2 đoạn CÙNG
   tầng/style mà xử lý thuật ngữ khác nhau.

2. trinh_bay_phu_hop: phải là văn xuôi liền mạch. Fail nếu có đánh số mục ("Mục 1:", "1.",
   "I."), gạch đầu dòng, hoặc câu chú thích về quá trình viết ("(mục này được tóm gọn vì...)").

3. bo_cuc_uu_tien_thu_tu: các mục phải đúng thứ tự gốc, xác định qua nội dung/chủ đề (bản tóm
   tắt không đánh số). Về gộp mục tầng "nền": nếu style là "binh_thuong", gộp nhiều mục nền
   liên tiếp thành 1 đoạn là ĐÚNG THIẾT KẾ, không fail. Nếu style là "chuyen_sau" hoặc
   "khong_chuyen_mon", gộp từ 2 mục nền trở lên thành 1 đoạn là VI PHẠM - PHẢI fail.

Chỉ trả JSON, không markdown, không chữ thừa:
{{
  "nhat_quan": {{"verdict": "pass", "ly_do": "..."}},
  "trinh_bay_phu_hop": {{"verdict": "pass", "ly_do": "..."}},
  "bo_cuc_uu_tien_thu_tu": {{"verdict": "pass", "ly_do": "..."}}
}}"""

    return prompt


def build_judge_prompt_theo_batch(persona, ket_qua_tom_tat, batch_muc, idx_batch, tong_batch):
    danh_sach_muc_text = dinh_dang_danh_sach_muc(batch_muc)

    ho_so = f"""
Ngành/lĩnh vực: {persona.get('nganh_to', '')} - {persona.get('nganh_nho', '')}
Đơn vị công tác: {persona.get('to_chuc', '')}
Mô tả chung: {persona.get('mo_ta_chung', '')}
Style tổng thể: {ket_qua_tom_tat.get('style')}
""".strip()

    prompt = f"""Giám khảo chấm bản tóm tắt cá nhân hóa văn bản hành chính. Đợt {idx_batch}/{tong_batch}
- CHỈ chấm phần tương ứng với các [MỤC N] dưới đây, các mục khác không thuộc phạm vi. Mỗi tiêu
chí trả "verdict": pass/fail kèm "ly_do" (trích dẫn cụ thể, PHẢI dựa trên nội dung THỰC SỰ có
trong [MỤC N] gốc hoặc bản tóm tắt, không suy diễn).

HỒ SƠ: {ho_so}

CÁC MỤC ĐỢT NÀY (tầng ghi kèm là tầng YÊU CẦU theo thiết kế, dùng làm căn cứ chấm):
{danh_sach_muc_text}

BẢN TÓM TẮT (văn xuôi liền mạch không đánh số - tự xác định đoạn ứng với từng mục qua nội
dung/chủ đề/tên cơ quan; đoạn ứng với mục KHÔNG thuộc đợt này thì bỏ qua):
\"\"\"
{ket_qua_tom_tat.get('summary')}
\"\"\"

TIÊU CHÍ:

1. chon_loc_phu_hop: mục tầng "chuyên sâu"/"trung bình" phải có nội dung xuất hiện đầy đủ,
   không bỏ sót ý quan trọng - nếu thiếu, trích [MỤC N] và nội dung cụ thể bị thiếu. KHÔNG áp
   dụng cho mục tầng "nền" dưới bất kỳ style nào - bỏ qua hoàn toàn, không lấy làm căn cứ fail
   ở tiêu chí này (đánh giá riêng ở tiêu chí 2). Không phàn nàn nội dung không tồn tại trong
   các [MỤC N] thuộc đợt này.

2. bo_cuc_chi_tiet_theo_tang: mục tầng "chuyên sâu" phải giữ chi tiết cụ thể (số liệu, mốc
   thời gian, tên đơn vị, nhiệm vụ). Số hiệu/ký hiệu/ngày ban hành văn bản viện dẫn (vd
   "777/TTg-TCCV") KHÔNG tính là chi tiết cần giữ - lược bỏ là ĐÚNG, không fail vì thiếu số hiệu.
   Mục tầng "nền": nếu style "binh_thuong" - không bắt buộc giữ số liệu/mốc thời gian/tên đơn
   vị chi tiết, chỉ không được bỏ hẳn cả mục/nhóm nội dung lớn. ĐƯỢC PHÉP rút gọn danh sách
   nhiều đối tượng cùng loại lặp theo mẫu (vd nhiều dòng "sáp nhập X, Y vào Z") bằng 1-2 ví dụ
   tiêu biểu + "và tương tự cho các... khác" - không fail vì thiếu tên từng đối tượng, miễn ý
   chính (có việc sáp nhập/hợp nhất, số lượng nếu có) còn giữ. Nếu style "chuyen_sau"/
   "khong_chuyen_mon" - mục tầng nền PHẢI giữ chi tiết như tầng chuyên sâu, không tóm chung
   chung.
   CHỈ fail khi trích được ÍT NHẤT MỘT chi tiết cụ thể có trong [MỤC N] nhưng không có trong
   bản tóm tắt, kèm câu trích nguyên văn từ bản tóm tắt làm bằng chứng thiếu. Không trích được
   thì để pass.

3. giong_dieu_phu_hop: PHẠM VI CỦA TIÊU CHÍ NÀY CHỈ LÀ TỪ VIẾT TẮT (dạng chữ hoa liền nhau,
   vd UBND, HĐND, BHXH, BHYT, UBMTTQ, GD&ĐT...) - KHÔNG xét bất kỳ thuật ngữ/cụm từ nào khác
   dù nghe có vẻ chuyên ngành hay hành chính (vd "đề án", "sáp nhập", "thẩm định", "quy hoạch
   tổng thể", "xã hội hóa"...) - các cụm này KHÔNG bắt buộc giải thích, KHÔNG được lấy làm
   căn cứ fail dưới bất kỳ hình thức nào.
   TUYỆT ĐỐI KHÔNG fail vì tên/số hiệu văn bản viện dẫn (vd "Nghị định 21/TW", "Nghị quyết
   71-NQ/TW", "Quyết định 777/TTg-TCCV", "Kế hoạch 1186/KH-BGDĐT") - đây KHÔNG phải từ viết
   tắt cần giải thích, dù có ghi kèm loại văn bản (Nghị định, Nghị quyết, Quyết định, Kế
   hoạch...) cũng không fail vì lý do này. QUAN TRỌNG: điều này áp dụng CẢ KHI chỉ một MẢNH
   của số hiệu văn bản xuất hiện tách rời (không kèm số phía trước) - vd "TTg", "TCCV", "NQ",
   "NQ/TW", "NQ-HĐND", "NĐ-CP", "QĐ-UBND", "KH-BGDĐT" là các mảnh ký hiệu LOẠI văn bản/cơ quan
   ban hành, KHÔNG PHẢI từ viết tắt tên cơ quan/tổ chức độc lập cần giải thích - TUYỆT ĐỐI
   KHÔNG fail vì các mảnh này thiếu giải thích, kể cả khi chúng trông giống chữ viết hoa liền
   nhau.
   Tầng "chuyên sâu" dùng từ viết tắt tự nhiên không cần giải thích.
   Tầng nền theo style: "chuyen_sau" - từ viết tắt hành chính PHỔ BIẾN (UBND, HĐND...) không
   cần giải thích, chỉ fail nếu dùng từ viết tắt CHUYÊN NGÀNH RIÊNG của lĩnh vực khác mà
   không giải thích. "khong_chuyen_mon"/"binh_thuong" (và tầng "trung bình" dưới mọi style) -
   PHẢI giải thích từ viết tắt hành chính ngay khi xuất hiện lần đầu trong đoạn.
   CHỈ fail khi trích được nguyên văn ĐÚNG 1 từ viết tắt cụ thể còn thiếu giải thích trong bản
   tóm tắt - không được fail vì lý do chung chung kiểu "chưa giải thích đầy đủ thuật ngữ" mà
   không chỉ ra được từ viết tắt cụ thể nào. Không trích được từ viết tắt cụ thể thì để pass.

4. thai_do_dung_dan: không tự suy luận, đánh giá, thêm nhận định không có trong [MỤC N] gốc.

Chỉ trả JSON, không markdown, không chữ thừa:
{{
  "chon_loc_phu_hop": {{"verdict": "pass", "ly_do": "..."}},
  "bo_cuc_chi_tiet_theo_tang": {{"verdict": "pass", "ly_do": "..."}},
  "giong_dieu_phu_hop": {{"verdict": "pass", "ly_do": "..."}},
  "thai_do_dung_dan": {{"verdict": "pass", "ly_do": "..."}}
}}"""

    return prompt

async def _goi_judge(client, semaphore, model_name, prompt, nhan):
    so_ky_tu = len(prompt)
    so_token_uoc_luong = uoc_luong_so_token(prompt)
    print(f"[DEBUG] {nhan}: prompt {so_ky_tu} ký tự (~{so_token_uoc_luong} token ước lượng)")

    async def _goi(max_tokens):
        async def _call():
            return await client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                    "max_output_tokens": max_tokens,
                },
            )

        async with semaphore:
            try:
                return await retry_generate_async(_call)
            except Exception as loi:
                print(f"[DEBUG-LỖI] {nhan}: gọi LLM thất bại sau hết retry ({loi}). max_output_tokens={max_tokens}.")
                raise

    response = await _goi(EVAL_MAX_OUTPUT_TOKENS)
    if getattr(response, "finish_reason", None) == "length":
        print(f"[DEBUG] {nhan}: output bị cắt cụt ở {EVAL_MAX_OUTPUT_TOKENS} token, thử lại với {EVAL_MAX_OUTPUT_TOKENS_MO_RONG} token.")
        response = await _goi(EVAL_MAX_OUTPUT_TOKENS_MO_RONG)

    raw = response.text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError:
        return None, raw


def _gop_ket_qua_cham(cham_tong_the, cac_cham_batch):

    def _gop_theo_batch(khoa):
        fail_list = []
        so_pass = 0
        tong = len(cac_cham_batch)
        for i, cham_batch in enumerate(cac_cham_batch, 1):
            ket = cham_batch.get(khoa, {"verdict": "fail", "ly_do": "LỖI: thiếu kết quả chấm đợt này."})
            if ket.get("verdict") == "fail":
                fail_list.append(f"[đợt {i}] {ket.get('ly_do', '')}")
            else:
                so_pass += 1

        if tong == 0:
            return {"verdict": "fail", "ly_do": "Không có đợt nào chấm được."}

        ti_le_pass = so_pass / tong
        if ti_le_pass >= NGUONG_TI_LE_PASS_BATCH:
            ly_do = f"Đạt {so_pass}/{tong} đợt (≥{int(NGUONG_TI_LE_PASS_BATCH * 100)}%)."
            if fail_list:
                ly_do += " Đợt fail (không ảnh hưởng verdict do đạt ngưỡng): " + " | ".join(fail_list)
            return {"verdict": "pass", "ly_do": ly_do}
        return {
            "verdict": "fail",
            "ly_do": (
                f"Chỉ đạt {so_pass}/{tong} đợt (<{int(NGUONG_TI_LE_PASS_BATCH * 100)}%): "
                + " | ".join(fail_list)
            ),
        }

    chon_loc_phu_hop = _gop_theo_batch("chon_loc_phu_hop")
    giong_dieu_phu_hop = _gop_theo_batch("giong_dieu_phu_hop")
    thai_do_dung_dan = _gop_theo_batch("thai_do_dung_dan")
    bo_cuc_chi_tiet = _gop_theo_batch("bo_cuc_chi_tiet_theo_tang")

    bo_cuc_thu_tu = cham_tong_the.get(
        "bo_cuc_uu_tien_thu_tu", {"verdict": "fail", "ly_do": "LỖI: thiếu kết quả chấm tổng thể."}
    )
    if bo_cuc_thu_tu.get("verdict") == "fail" or bo_cuc_chi_tiet.get("verdict") == "fail":
        ly_do_gop = []
        if bo_cuc_thu_tu.get("verdict") == "fail":
            ly_do_gop.append(f"[thứ tự] {bo_cuc_thu_tu.get('ly_do', '')}")
        if bo_cuc_chi_tiet.get("verdict") == "fail":
            ly_do_gop.append(f"[chi tiết theo tầng] {bo_cuc_chi_tiet.get('ly_do', '')}")
        bo_cuc_uu_tien = {"verdict": "fail", "ly_do": " | ".join(ly_do_gop)}
    else:
        bo_cuc_uu_tien = {"verdict": "pass", "ly_do": "Đạt cả thứ tự lẫn chi tiết theo tầng."}

    return {
        "chon_loc_phu_hop": chon_loc_phu_hop,
        "nhat_quan": cham_tong_the.get("nhat_quan", {"verdict": "fail", "ly_do": "LỖI: thiếu kết quả chấm tổng thể."}),
        "trinh_bay_phu_hop": cham_tong_the.get("trinh_bay_phu_hop", {"verdict": "fail", "ly_do": "LỖI: thiếu kết quả chấm tổng thể."}),
        "bo_cuc_uu_tien": bo_cuc_uu_tien,
        "giong_dieu_phu_hop": giong_dieu_phu_hop,
        "thai_do_dung_dan": thai_do_dung_dan,
    }


async def cham_1_ban_tom_tat(persona, ket_qua_tom_tat, client, semaphore, model_name=OSS_MODEL_NAME):
    danh_sach_muc_goc = ket_qua_tom_tat.get("danh_sach_muc_voi_tang", [])
    danh_sach_muc_loc = loc_muc_hop_le(danh_sach_muc_goc)

    if "danh_sach_muc_voi_tang" not in ket_qua_tom_tat:
        return {
            "id": persona.get("id"),
            "note": (
                "Bỏ qua đánh giá - file summary này thiếu field "
                "'danh_sach_muc_voi_tang' (được tạo TRƯỚC khi personalize có patch "
                "lưu field này). Cần chạy lại tom_tat_hanh_chinh_cho_persona cho "
                "văn bản/persona này rồi mới chấm được."
            ),
        }

    if not danh_sach_muc_loc:
        return {
            "id": persona.get("id"),
            "note": (
                "Bỏ qua đánh giá - danh_sach_muc_voi_tang rỗng sau khi lọc mục "
                "hợp lệ (0 mục có nội dung). Kiểm tra lại bước extract/personalize "
                "cho văn bản này, có thể lỗi trích xuất docx."
            ),
        }

    summary = ket_qua_tom_tat.get("summary", "")
    if not summary:
        return {
            "id": persona.get("id"),
            "note": "Bỏ qua đánh giá - bản tóm tắt rỗng.",
        }

    nhan = f"{persona.get('id')} — file {ket_qua_tom_tat.get('file')}"

    prompt_tong_the = build_judge_prompt_tong_the(persona, ket_qua_tom_tat, danh_sach_muc_loc)
    cac_batch_muc = _chia_muc_theo_token_cham(danh_sach_muc_loc)

    async def _cham_tong_the():
        return await _goi_judge(client, semaphore, model_name, prompt_tong_the, f"{nhan} (tổng thể)")

    async def _cham_1_batch(batch_muc, idx_batch):
        prompt_batch = build_judge_prompt_theo_batch(
            persona, ket_qua_tom_tat, batch_muc, idx_batch, len(cac_batch_muc)
        )
        return await _goi_judge(
            client, semaphore, model_name, prompt_batch, f"{nhan} (đợt {idx_batch}/{len(cac_batch_muc)})"
        )

    (cham_tong_the, raw_tong_the), *cac_ket_qua_batch = await asyncio.gather(
        _cham_tong_the(),
        *[_cham_1_batch(batch, i) for i, batch in enumerate(cac_batch_muc, 1)]
    )

    loi_dinh_dang = []
    raw_loi = {}

    canh_bao_hau_kiem = []

    if cham_tong_the is None:
        loi_dinh_dang.append("tong_the")
        raw_loi["tong_the"] = raw_tong_the
        cham_tong_the = {
            khoa: {"verdict": "fail", "ly_do": "LỖI: judge trả JSON không hợp lệ cho lượt chấm tổng thể, cần soát tay."}
            for khoa in ("nhat_quan", "trinh_bay_phu_hop", "bo_cuc_uu_tien_thu_tu")
        }
    else:
        cham_tong_the, canh_bao_tong_the = hau_kiem_va_sua_batch("tổng thể", cham_tong_the, summary)
        canh_bao_hau_kiem.extend(canh_bao_tong_the)

    style_hien_tai = ket_qua_tom_tat.get("style")
    if style_hien_tai in ("chuyen_sau", "khong_chuyen_mon"):
        cham_tong_the["bo_cuc_uu_tien_thu_tu"] = {
            "verdict": "pass",
            "ly_do": (
                f"[TỰ ĐỘNG XÁC NHẬN - style {style_hien_tai}] Thứ tự mục và việc KHÔNG gộp "
                f"mục nền được đảm bảo 100% bằng code (mỗi mục = 1 lượt gọi LLM riêng, Python "
                f"nối lại đúng thứ tự index gốc), không phụ thuộc model - bỏ qua verdict gốc "
                f"của judge cho tiêu chí này (nếu có)."
            ),
        }

    cac_cham_batch = []
    for i, (ket_qua_batch, raw_batch) in enumerate(cac_ket_qua_batch, 1):
        if ket_qua_batch is None:
            loi_dinh_dang.append(f"batch_{i}")
            raw_loi[f"batch_{i}"] = raw_batch
            ket_qua_batch = {
                khoa: {"verdict": "fail", "ly_do": "LỖI: judge trả JSON không hợp lệ cho đợt này, cần soát tay."}
                for khoa in ("chon_loc_phu_hop", "bo_cuc_chi_tiet_theo_tang", "giong_dieu_phu_hop", "thai_do_dung_dan")
            }
        else:
            ket_qua_batch, canh_bao_batch = hau_kiem_va_sua_batch(f"đợt {i}", ket_qua_batch, summary)
            canh_bao_hau_kiem.extend(canh_bao_batch)
        cac_cham_batch.append(ket_qua_batch)

    cham = _gop_ket_qua_cham(cham_tong_the, cac_cham_batch)

    so_dat = sum(1 for tc in TIEU_CHI if cham.get(tc, {}).get("verdict") == "pass")

    ket_qua_cham = {
        "id": persona.get("id"),
        "file": ket_qua_tom_tat.get("file"),
        "so_batch_cham": len(cac_batch_muc),
        "tieu_chi": cham,
        "so_tieu_chi_dat": so_dat,
        "verdict_cuoi": "DAT" if so_dat == len(TIEU_CHI) else "KHONG_DAT",
    }
    if loi_dinh_dang:
        ket_qua_cham["canh_bao_loi_dinh_dang"] = (
            f"Các lần gọi judge trả sai JSON (đã bỏ qua, coi các tiêu chí liên quan là fail "
            f"mặc định): {', '.join(loi_dinh_dang)}. raw_response đã lưu riêng để soát tay."
        )
        ket_qua_cham["raw_response_loi"] = raw_loi

    ly_do_hau_kiem = hau_kiem_dinh_dang(summary) + canh_bao_hau_kiem
    if ly_do_hau_kiem:
        ket_qua_cham["can_soat_tay"] = True
        ket_qua_cham["hau_kiem_canh_bao"] = ly_do_hau_kiem

    return ket_qua_cham


def in_ket_qua_cham(persona_id, cham):
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

    parser = argparse.ArgumentParser(description="Đánh giá bản tóm tắt hành chính bằng LLM Judge")
    parser.add_argument("--file", required=True, help="tên file docx văn bản hành chính (không cần đường dẫn đầy đủ)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", help="id của persona, ví dụ NN0001")
    group.add_argument("--so-luong", type=int, help="chấm từ persona đầu tiên đến persona thứ n")
    parser.add_argument("--variant", type=str, default=None, help="ten bien the persona")
    args = parser.parse_args()

    duong_dan_file = Path(args.file)
    if not duong_dan_file.exists():
        duong_dan_file = ROOT_DIR / "data" / "hanh_chinh" / duong_dan_file
    ten_file_goc = duong_dan_file.stem

    if args.variant:
        SUMMARY_DIR = ROOT_DIR / "output" / "hanh_chinh" / "summary" / args.variant / ten_file_goc
        EVAL_DIR = ROOT_DIR / "output" / "hanh_chinh" / "eval" / args.variant / ten_file_goc
    else:
        SUMMARY_DIR = ROOT_DIR / "output" / "hanh_chinh" / "summary" / ten_file_goc
        EVAL_DIR = ROOT_DIR / "output" / "hanh_chinh" / "eval" / ten_file_goc
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    if not SUMMARY_DIR.exists():
        raise SystemExit(f"Không tìm thấy thư mục summary cho văn bản này: {SUMMARY_DIR}")

    ten_file_persona = f"state_profiles_{args.variant}.json" if args.variant else "state_profiles_nt_nn_tc_kn_cd_ch.json"
    duong_dan_persona = ROOT_DIR / "data" / "profile" / ten_file_persona
    with open(duong_dan_persona, encoding="utf-8") as f:
        personas = json.load(f)
    persona_index = {p["id"]: p for p in personas}

    if args.id:
        personas_can_cham = [args.id]
    else:
        personas_can_cham = [p["id"] for p in personas[:args.so_luong]]


    async def xu_ly_mot_persona(client, semaphore, persona_id, i, tong, ket_qua_tong):
        out_path = EVAL_DIR / f"{persona_id}.json"
        if out_path.exists():
            print(f"[{i}/{tong}] {persona_id} đã chấm rồi -> bỏ qua")
            return

        summary_path = SUMMARY_DIR / f"{persona_id}.json"
        if not summary_path.exists():
            print(f"[{i}/{tong}] {persona_id} chưa có file summary -> bỏ qua")
            ket_qua_tong["bo_qua"] += 1
            return

        persona = persona_index.get(persona_id)
        if persona is None:
            print(f"[{i}/{tong}] {persona_id} không tìm thấy trong profile -> bỏ qua")
            ket_qua_tong["bo_qua"] += 1
            return

        with open(summary_path, encoding="utf-8") as f:
            ket_qua_tom_tat = json.load(f)

        print(f"[{i}/{tong}] {persona_id} đang chấm...")
        try:
            cham = await cham_1_ban_tom_tat(persona, ket_qua_tom_tat, client, semaphore)
        except Exception as loi:
            print(f"[{i}/{tong}] {persona_id} bỏ qua do lỗi gọi LLM: {loi}")
            ket_qua_tong["bo_qua"] += 1
            return

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cham, f, ensure_ascii=False, indent=2)

        in_ket_qua_cham(persona_id, cham)
        if cham.get("verdict_cuoi") == "DAT":
            ket_qua_tong["dat"] += 1
        elif cham.get("verdict_cuoi") == "KHONG_DAT":
            ket_qua_tong["khong_dat"] += 1
        else:
            ket_qua_tong["bo_qua"] += 1


    async def chay():
        client = tao_oss_client_async()
        semaphore = asyncio.Semaphore(OSS_MAX_CONCURRENCY_SUMMARY)
        tong = len(personas_can_cham)
        ket_qua_tong = {"dat": 0, "khong_dat": 0, "bo_qua": 0}

        tasks = [
            xu_ly_mot_persona(client, semaphore, persona_id, i, tong, ket_qua_tong)
            for i, persona_id in enumerate(personas_can_cham, start=1)
        ]
        await asyncio.gather(*tasks)
        return ket_qua_tong


    t_bat_dau = time.time()
    ket_qua_tong = asyncio.run(chay())

    print("\nXONG HẾT. Tổng thời gian:", round((time.time() - t_bat_dau) / 60, 1), "phút")
    print(f"ĐẠT cả 6 tiêu chí: {ket_qua_tong['dat']}")
    print(f"KHÔNG ĐẠT: {ket_qua_tong['khong_dat']}")
    print(f"Bỏ qua: {ket_qua_tong['bo_qua']}")