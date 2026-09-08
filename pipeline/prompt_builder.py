"""
prompt_builder.py
Ghép ontology_context + 2 thế giới + community + văn bản gốc thành prompt.
"""

from pipeline.community import determine_community
from pipeline.worlds import build_worlds
from pipeline.ontology_context import build_ontology_context, load_graph

import json
import os

_GENRE_DOMAIN_MAP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "genre_domain_map.json"
)
with open(_GENRE_DOMAIN_MAP_PATH, encoding="utf-8") as f:
    GENRE_DOMAIN_MAP = json.load(f)


def build_prompt(row: dict, text: str, g, content_meta: dict = None) -> str:
    community        = determine_community(row)
    worlds           = build_worlds(row)
    ontology_context = build_ontology_context(g)

    xac_nhan  = worlds["xac_nhan"]
    gia_tuong = worlds["gia_tuong"]

    # ── Chiều Language → chỉ dẫn văn phong ──────────────────────────────────
    lang_level = community["Language"]["level"]
    lang_desc  = community["Language"]["description"]

    lang_instruction_map = {
        1: "Dùng ngôn ngữ đơn giản, câu ngắn, từ ngữ đời thường. Tuyệt đối không dùng thuật ngữ chuyên môn.",
        2: "Dùng ngôn ngữ rõ ràng, dễ hiểu. Hạn chế thuật ngữ chuyên môn, nếu có thì giải thích ngắn gọn.",
        3: "Có thể dùng thuật ngữ phổ thông. Lập luận rõ ràng, cụ thể.",
        4: "Có thể dùng thuật ngữ chuyên môn. Lập luận nhiều tầng, giữ lại số liệu và chi tiết kỹ thuật.",
    }

    lang_instruction = lang_instruction_map[lang_level]

    # ── Chiều Topic → nội dung ưu tiên giữ lại ──────────────────────────────
    topic_str = ", ".join(community["Topic"][:3])

    # ── Chiều Domain → độ sâu chuyên môn ────────────────────────────────────
    domain_str = ", ".join(community["Domain"])

    # ── Chiều Cultural → góc độ văn hóa ─────────────────────────────────────
    cultural_str = community["Cultural"]["context"]

    # ── Chiều Prototype → mô tả tổng hợp ────────────────────────────────────
    prototype_str = community["Prototype"]

    prompt = f"""Bạn là hệ thống tóm tắt văn bản cá nhân hóa. Nhiệm vụ của bạn là tóm tắt văn bản đầu vào sao cho phù hợp với đúng người dùng được mô tả dưới đây.

═══════════════════════════════════════════════
PHẦN 1: KHUNG PHÂN TÍCH PERSONA (Ontology Context)
═══════════════════════════════════════════════
Đây là cấu trúc các đặc điểm persona và mối quan hệ giữa chúng. Dùng để hiểu cách các yếu tố của người dùng liên kết với nhau:

{ontology_context}

═══════════════════════════════════════════════
PHẦN 2: HỒ SƠ NGƯỜI DÙNG
═══════════════════════════════════════════════

[Hình mẫu đại diện]
{prototype_str}

[Thế giới xác nhận — thông tin chính xác, bắt buộc phản ánh đúng]
{xac_nhan["statement"]}

[Thế giới giả tưởng — động lực và định hướng nội tâm]
• Bổn phận: {gia_tuong["Bổn phận"]}
• Mong muốn: {gia_tuong["Mong muốn"]}
• Niềm tin: {gia_tuong["Niềm tin"]}

═══════════════════════════════════════════════
PHẦN 3: CHỈ DẪN TÓM TẮT
═══════════════════════════════════════════════

Văn phong: {lang_instruction} (Đặc điểm người nhận: {lang_desc})
Chủ đề ưu tiên giữ lại: {topic_str}
Lĩnh vực người dùng đã am hiểu (không cần giải thích cơ bản): {domain_str}
Góc độ văn hóa: {cultural_str}

Nguyên tắc bắt buộc:
1. Chỉ giữ lại thông tin phù hợp với hồ sơ người dùng trên.
2. Lược bỏ nội dung không liên quan đến chủ đề ưu tiên.
3. Không thêm thông tin ngoài văn bản gốc. Persona chỉ là "màng lọc" để quyết định giữ lại gì, không phải để sáng tác thêm.
4. Không giải thích lại những gì người dùng đã thành thạo trong lĩnh vực: {domain_str}.
5. Phản ánh đúng thế giới xác nhận — không suy diễn thêm về người dùng.
6. Ưu tiên nội dung theo thứ bậc: đặc trưng cứng (tuổi, trình độ học vấn, nghề nghiệp, khu vực sống) có trọng số cao hơn đặc trưng mềm (sở thích du lịch, nghệ thuật, thể thao). Khi hai nhóm gợi ý nội dung mâu thuẫn, giữ lại nội dung phù hợp với đặc trưng cứng, lược bỏ nội dung chỉ phù hợp với đặc trưng mềm.

═══════════════════════════════════════════════
PHẦN 4: VĂN BẢN GỐC CẦN TÓM TẮT
═══════════════════════════════════════════════

{text}

═══════════════════════════════════════════════
Hãy viết bản tóm tắt cá nhân hóa cho người dùng trên. Chỉ trả về bản tóm tắt, không giải thích thêm.
"""
    return prompt

def build_neutral_prompt(text: str) -> str:
    n_words = len(text.split())
    max_words = int(n_words * 0.7)
    return f"""Bạn là hệ thống tóm tắt văn bản khách quan.

Hãy tóm tắt văn bản dưới đây một cách trung lập, đầy đủ ý chính, không thiên vị
theo bất kỳ góc nhìn cá nhân nào. Độ dài bản tóm tắt tối đa bằng 70% số từ của
văn bản gốc. Không thêm thông tin ngoài văn bản gốc.

═══════════════════════════════════════════════
VĂN BẢN GỐC CẦN TÓM TẮT
═══════════════════════════════════════════════

{text}

═══════════════════════════════════════════════
Hãy viết bản tóm tắt khách quan. Chỉ trả về bản tóm tắt, không giải thích thêm.
Độ dài bản tóm tắt KHÔNG ĐƯỢC VƯỢT QUÁ {max_words} từ (bản gốc có {n_words} từ).
"""

# ── TEST ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pandas as pd

    g = load_graph("../ontology/persona_analysis_2_1.ttl")
    df = pd.read_csv("../data/sample50.csv")

    sample_text = """Lễ hội pháo hoa quốc tế Đà Nẵng năm nay dự kiến diễn ra từ ngày 31/5 đến 12/7,
với sự tham gia của 8 đội đến từ các quốc gia như Ý, Úc, Mỹ, Phần Lan và Việt Nam.
Ban tổ chức cho biết lễ hội năm nay sẽ có thêm khu vực trải nghiệm ẩm thực đường phố
kết hợp với các gian hàng thủ công mỹ nghệ truyền thống. Vé xem pháo hoa dao động từ
200.000 đến 800.000 đồng tùy vị trí khán đài. Ngoài ra, du khách đến từ các tỉnh thành
khác có thể đặt tour trọn gói bao gồm vé máy bay, khách sạn và vé xem pháo hoa thông
qua các đại lý du lịch. Ban tổ chức khuyến cáo người xem nên đến sớm ít nhất 1 tiếng
để tìm chỗ đỗ xe và ổn định chỗ ngồi, đồng thời chuẩn bị áo mưa vì thời tiết tháng 6
tại Đà Nẵng thường có mưa bất chợt."""

    row = df.iloc[2].to_dict()
    prompt = build_prompt(row, sample_text, g)
    print(prompt)
    print(f"\n--- Tổng độ dài prompt: {len(prompt)} ký tự ---")