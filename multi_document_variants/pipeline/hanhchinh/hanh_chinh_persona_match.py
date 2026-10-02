"""
File: pipeline/rss/hanhchinh/hanh_chinh_persona_match.py

Mục đích: so khớp "đối tượng thi hành" trích từ hanh_chinh_extract.py
với nganh_to/nganh_nho trong state_profiles.json bằng LLM, sau đó lọc
ra danh sách persona_id liên quan.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from pipeline.utils import retry_generate
from pipeline.hanhchinh.hanh_chinh_extract import xu_ly_1_file

load_dotenv()
API_KEY = os.getenv("API_KEY")
client = genai.Client(api_key=API_KEY)

MODEL_NAME_KHOP_NGANH = "gemini-3.1-flash-lite"
ROOT_DIR = Path(__file__).resolve().parents[3]
PROFILE_PATH = ROOT_DIR / "data" / "state_profiles.json"


def lay_danh_sach_nganh(duong_dan_profile=PROFILE_PATH):
    """Đọc state_profiles.json, trả về danh sách nganh_to duy nhất
    và dict {nganh_to: [danh sách nganh_nho duy nhất]}"""
    with open(duong_dan_profile, "r", encoding="utf-8") as f:
        du_lieu = json.load(f)

    nganh_to_set = set()
    nganh_to_sang_nganh_nho = {}

    for persona in du_lieu:
        nganh_to = persona.get("nganh_to")
        nganh_nho = persona.get("nganh_nho")
        if not nganh_to:
            continue
        nganh_to_set.add(nganh_to)
        nganh_to_sang_nganh_nho.setdefault(nganh_to, set()).add(nganh_nho)

    nganh_to_sang_nganh_nho = {
        k: sorted(v) for k, v in nganh_to_sang_nganh_nho.items()
    }
    return sorted(nganh_to_set), nganh_to_sang_nganh_nho


def tao_prompt_khop_nganh_gop(danh_sach_doi_tuong, danh_sach_nganh_to, nganh_to_sang_nganh_nho, trich_yeu=None):
    """Tạo prompt khớp NHIỀU đối tượng thi hành cùng lúc (1 lần gọi LLM 
    cho cả văn bản), mỗi đối tượng đánh số thứ tự để LLM trả kết quả 
    tương ứng. Nếu có trich_yeu (chủ đề công văn), đưa vào làm ngữ cảnh 
    chung để khớp ngành chính xác hơn khi đối tượng thi hành chỉ nêu 
    chung chung."""
    danh_sach_nganh_text = ""
    for nganh_to in danh_sach_nganh_to:
        danh_sach_nho = nganh_to_sang_nganh_nho.get(nganh_to, [])
        danh_sach_nganh_text += f"- {nganh_to}: {', '.join(danh_sach_nho)}\n"

    danh_sach_doi_tuong_text = ""
    for i, doi_tuong in enumerate(danh_sach_doi_tuong):
        danh_sach_doi_tuong_text += f"{i}. \"{doi_tuong['text']}\"\n"

    boi_canh_text = ""
    if trich_yeu:
        boi_canh_text = f"""Ngữ cảnh chung: văn bản này có trích yếu (chủ đề) là:
"{trich_yeu}"
Hãy dùng ngữ cảnh này để khớp ngành chính xác hơn, đặc biệt khi câu đối 
tượng thi hành chỉ nêu chung chung (vd "các Sở, Ban, ngành") mà không 
nêu tên cơ quan cụ thể - trong trường hợp đó, chỉ chọn nganh_to/nganh_nho 
THỰC SỰ liên quan đến chủ đề trích yếu, không liệt kê tất cả.

"""

    prompt = f"""Bạn là trợ lý phân loại hành chính. Dưới đây là danh sách 
các câu mô tả đối tượng thi hành trích từ MỘT văn bản hành chính, mỗi 
câu đánh số thứ tự:

{boi_canh_text}{danh_sach_doi_tuong_text}

Danh sách ngành (nganh_to) và các ngành nhỏ (nganh_nho) tương ứng:
{danh_sach_nganh_text}

Nhiệm vụ: Với TỪNG câu theo đúng số thứ tự, xác định câu đó khớp với 
(những) nganh_to và nganh_nho nào trong danh sách trên. Nếu câu chỉ nhắc 
chung chung (vd "các Sở, ban, ngành", "Thủ trưởng các đơn vị") và KHÔNG 
có ngữ cảnh chung ở trên để thu hẹp, thì liệt kê TẤT CẢ nganh_to phù hợp. 
Nếu CÓ ngữ cảnh chung (trích yếu), ưu tiên dùng nó để chỉ chọn ngành 
thực sự liên quan đến chủ đề, không liệt kê tất cả. Mỗi câu xử lý độc 
lập, không suy luận chéo giữa các câu (trừ việc dùng ngữ cảnh chung ở trên).

Chỉ trả về JSON, không giải thích, không markdown, đúng định dạng sau 
(mảng có đúng số phần tử bằng số câu, đúng thứ tự):
[
  {{
    "stt": 0,
    "nganh_to_khop": ["ten nganh to 1"],
    "nganh_nho_khop": ["ten nganh nho 1"],
    "do_tin_cay": "cao"
  }},
  {{
    "stt": 1,
    "nganh_to_khop": [],
    "nganh_nho_khop": [],
    "do_tin_cay": "thap"
  }}
]"""
    return prompt


def goi_llm_khop_nganh_gop(client, danh_sach_doi_tuong, danh_sach_nganh_to, nganh_to_sang_nganh_nho, trich_yeu=None):
    """Gọi Gemini 1 lần để khớp TẤT CẢ đối tượng thi hành của 1 văn bản.
    Trả về list kết quả theo đúng thứ tự đầu vào. Nếu có trich_yeu (chủ 
    đề công văn), truyền vào để làm ngữ cảnh chung giúp khớp ngành chính 
    xác hơn khi đối tượng thi hành chỉ nêu chung chung."""
    if not danh_sach_doi_tuong:
        return []

    prompt = tao_prompt_khop_nganh_gop(
        danh_sach_doi_tuong, danh_sach_nganh_to, nganh_to_sang_nganh_nho, trich_yeu=trich_yeu
    )

    def _call():
        return client.models.generate_content(
            model=MODEL_NAME_KHOP_NGANH,
            contents=prompt,
            config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )

    response = retry_generate(_call)
    text_tra_ve = response.text.strip()

    try:
        ket_qua_list = json.loads(text_tra_ve)
    except json.JSONDecodeError:
        print("LỖI PARSE JSON khi khớp ngành gộp cho văn bản")
        print(f"Text trả về: {text_tra_ve}")
        ket_qua_list = [
            {"stt": i, "nganh_to_khop": [], "nganh_nho_khop": [], "do_tin_cay": "thap"}
            for i in range(len(danh_sach_doi_tuong))
        ]

    if len(ket_qua_list) != len(danh_sach_doi_tuong):
        print(f"CẢNH BÁO: số kết quả ({len(ket_qua_list)}) không khớp "
              f"số đối tượng thi hành đầu vào ({len(danh_sach_doi_tuong)})")

    return ket_qua_list


def loc_persona_theo_ket_qua_khop(ket_qua_khop, duong_dan_profile=PROFILE_PATH):
    """Lọc danh sách persona_id từ state_profiles.json khớp với 
    nganh_to_khop / nganh_nho_khop"""
    with open(duong_dan_profile, "r", encoding="utf-8") as f:
        du_lieu = json.load(f)

    nganh_to_khop = set(ket_qua_khop.get("nganh_to_khop", []))
    nganh_nho_khop = set(ket_qua_khop.get("nganh_nho_khop", []))

    danh_sach_id_khop = []
    for persona in du_lieu:
        if persona.get("nganh_to") in nganh_to_khop or persona.get("nganh_nho") in nganh_nho_khop:
            danh_sach_id_khop.append(persona.get("id"))

    return danh_sach_id_khop


def chay_khop_persona_cho_van_ban(client, ket_qua_extract, duong_dan_profile=PROFILE_PATH):
    """Hàm điều phối chính: nhận output của hanh_chinh_extract.py
    (ket_qua_extract có field doi_tuong_thi_hanh), gọi LLM khớp gộp,
    rồi lọc persona_id tương ứng cho từng đối tượng thi hành.

    Trích yếu (nguon="trich_yeu") được tách riêng làm ngữ cảnh chung,
    không đưa vào danh sách khớp - vì bản thân nó không phải đối tượng
    thi hành, chỉ giúp thu hẹp phạm vi khi câu Kính gửi nêu chung chung.

    Trả về list, mỗi phần tử gồm: nguon, text (đối tượng thi hành gốc),
    nganh_to_khop, nganh_nho_khop, do_tin_cay, danh_sach_persona_id_khop"""
    danh_sach_doi_tuong_goc = ket_qua_extract.get("doi_tuong_thi_hanh", [])

    # tách trích yếu (nếu có) ra làm ngữ cảnh, không đưa vào khớp
    trich_yeu = None
    danh_sach_doi_tuong = []
    for dt in danh_sach_doi_tuong_goc:
        if dt.get("nguon") == "trich_yeu":
            trich_yeu = dt.get("text")
        else:
            danh_sach_doi_tuong.append(dt)

    danh_sach_nganh_to, nganh_to_sang_nganh_nho = lay_danh_sach_nganh(duong_dan_profile)

    ket_qua_khop_list = goi_llm_khop_nganh_gop(
        client, danh_sach_doi_tuong, danh_sach_nganh_to, nganh_to_sang_nganh_nho,
        trich_yeu=trich_yeu
    )

    ket_qua_cuoi_cung = []
    for i, doi_tuong in enumerate(danh_sach_doi_tuong):
        if i < len(ket_qua_khop_list):
            ket_qua_khop = ket_qua_khop_list[i]
        else:
            ket_qua_khop = {"nganh_to_khop": [], "nganh_nho_khop": [], "do_tin_cay": "thap"}

        danh_sach_id_khop = loc_persona_theo_ket_qua_khop(ket_qua_khop, duong_dan_profile)

        ket_qua_cuoi_cung.append({
            "nguon": doi_tuong.get("nguon"),
            "text": doi_tuong.get("text"),
            "nganh_to_khop": ket_qua_khop.get("nganh_to_khop", []),
            "nganh_nho_khop": ket_qua_khop.get("nganh_nho_khop", []),
            "do_tin_cay": ket_qua_khop.get("do_tin_cay", "thap"),
            "danh_sach_persona_id_khop": danh_sach_id_khop,
        })

    return ket_qua_cuoi_cung


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python -m pipeline.rss.hanhchinh.hanh_chinh_persona_match <đường_dẫn_file_docx>")
        sys.exit(1)

    duong_dan = Path(sys.argv[1])

    if not duong_dan.exists():
        duong_dan = ROOT_DIR / "data" / "hanh_chinh" / duong_dan

    print(f"Đang trích xuất văn bản hành chính từ: {duong_dan}")
    ket_qua_extract = xu_ly_1_file(str(duong_dan))

    print(f"Loại văn bản: {ket_qua_extract.get('loai_van_ban')}")
    print(f"Số lượng đối tượng thi hành: {len(ket_qua_extract.get('doi_tuong_thi_hanh', []))}")
    print("Đang gọi LLM khớp persona theo ngành...")

    ket_qua_khop = chay_khop_persona_cho_van_ban(client, ket_qua_extract)

    print("\n===== KẾT QUẢ KHỚP PERSONA =====")
    for item in ket_qua_khop:
        print(f"\nNguồn: {item['nguon']}")
        print(f"Text: {item['text']}")
        print(f"Nganh_to khớp: {item['nganh_to_khop']}")
        print(f"Nganh_nho khớp: {item['nganh_nho_khop']}")
        print(f"Độ tin cậy: {item['do_tin_cay']}")
        print(f"Số persona khớp: {len(item['danh_sach_persona_id_khop'])}")

    ten_file_json = duong_dan.with_name(f"{duong_dan.stem}_khop_persona.json")
    with open(ten_file_json, "w", encoding="utf-8") as f:
        json.dump(ket_qua_khop, f, ensure_ascii=False, indent=2)

    print(f"\nĐã lưu kết quả JSON tại: {ten_file_json}")