"""
worlds.py
Xây dựng 2 thế giới cho mỗi person:
1. Thế giới xác nhận — phát biểu chính xác từ trường HARD + thuộc tính bổ trợ
2. Thế giới giả tưởng — Bổn phận / Mong muốn / Niềm tin suy ra từ dữ liệu person
"""


# ── THẾ GIỚI XÁC NHẬN ────────────────────────────────────────────────────────

def build_confirmation_world(row: dict) -> dict:
    """
    Xây dựng thế giới xác nhận từ các trường HARD và thuộc tính bổ trợ cứng.
    Trả về dict gồm các phát biểu chính xác về person.
    Đây là thông tin cố định — bản tóm tắt phải phản ánh đúng, không được suy diễn.
    """
    age            = row["age"]
    sex            = row["sex"]
    education      = row["education_level"]
    occupation     = row["occupation"]
    country        = row["country"]
    region         = row["region"]
    zone           = row["zone"]
    marital_status = row["marital_status"]
    skills         = row["skills_and_expertise"]
    professional   = row["professional_persona"]

    # Xác định giai đoạn cuộc sống
    if age < 18:
        life_stage = "thiếu niên"
    elif age < 30:
        life_stage = "người trẻ"
    elif age < 50:
        life_stage = "người trung niên"
    elif age < 65:
        life_stage = "người lớn tuổi"
    else:
        life_stage = "người cao tuổi"

    # Xác định hoàn cảnh gia đình từ marital_status
    family_context_map = {
        "Độc thân":    "chưa lập gia đình",
        "Đã kết hôn":  "đã lập gia đình",
        "Góa":         "góa bụa",
        "Ly hôn":      "đã ly hôn",
        "Ly thân":     "đang ly thân",
    }
    family_context = family_context_map.get(marital_status, marital_status.lower())

    # Tóm tắt skills thành chuỗi ngắn (lấy 2 câu đầu)
    skills_summary = ". ".join(skills.split(".")[:2]).strip()
    if not skills_summary.endswith("."):
        skills_summary += "."

    # Tóm tắt professional_persona thành 1 câu đầu
    professional_summary = professional.split(".")[0].strip() + "."

    # Ghép thành phát biểu xác nhận
    statement = (
        f"{life_stage} {sex.lower()}, {age} tuổi, {family_context}, "
        f"trình độ {education.lower()}, nghề nghiệp: {occupation.lower()}, "
        f"sống tại {zone.lower()} {region}, {country}. "
        f"Chuyên môn: {skills_summary} "
        f"Bối cảnh nghề nghiệp: {professional_summary}"
    )

    return {
        # Các trường riêng lẻ để prompt_builder dùng linh hoạt
        "age":             age,
        "sex":             sex,
        "life_stage":      life_stage,
        "education":       education,
        "occupation":      occupation,
        "location":        f"{zone}, {region}, {country}",
        "marital_status":  marital_status,
        "family_context":  family_context,
        "skills_summary":  skills_summary,
        "professional":    professional_summary,
        # Phát biểu tổng hợp dùng trực tiếp trong prompt
        "statement":       statement,
    }


# ── THẾ GIỚI GIẢ TƯỞNG ───────────────────────────────────────────────────────

def _infer_duty(occupation: str, marital_status: str, age: int) -> str:
    """
    Bổn phận — suy từ occupation + marital_status + age.
    Phản ánh trách nhiệm và nghĩa vụ của person trong cuộc sống.
    """
    duty_parts = []

    # Nghĩa vụ gia đình
    if marital_status == "Đã kết hôn":
        if age < 50:
            duty_parts.append("xây dựng và duy trì cuộc sống gia đình")
        else:
            duty_parts.append("chăm lo cho gia đình và con cái")
    elif marital_status == "Góa":
        duty_parts.append("tự lo cho bản thân và duy trì các mối quan hệ gia đình")
    elif marital_status == "Độc thân":
        duty_parts.append("tự chủ về tài chính và phát triển bản thân")

    # Nghĩa vụ nghề nghiệp / xã hội
    occ_duty_map = {
        "Nghỉ hưu":                       "duy trì sức khỏe để sống độc lập và hỗ trợ thế hệ sau",
        "Buôn bán / kinh doanh":          "duy trì và phát triển hoạt động kinh doanh, tạo thu nhập ổn định",
        "Kỹ thuật viên / kỹ sư":          "đảm bảo chất lượng kỹ thuật và cập nhật kiến thức chuyên môn",
        "Y tế / dược":                    "chăm sóc sức khỏe cộng đồng và nâng cao năng lực chuyên môn",
        "Nghiên cứu / học thuật":         "đóng góp tri thức và đào tạo thế hệ kế tiếp",
        "Nông nghiệp / ngư nghiệp":       "duy trì sản xuất và đảm bảo thu nhập cho gia đình",
        "Công nhân / lao động phổ thông": "hoàn thành công việc và đảm bảo thu nhập ổn định",
        "Tài xế / giao hàng":             "đảm bảo an toàn giao thông và hoàn thành nhiệm vụ vận chuyển",
        "Freelancer / làm tự do":         "xây dựng uy tín nghề nghiệp và duy trì nguồn khách hàng ổn định",
        "Quản lý / kinh doanh":           "lãnh đạo đội nhóm và đạt mục tiêu kinh doanh",
        "Thất nghiệp / tìm việc":         "tìm kiếm việc làm phù hợp và duy trì cuộc sống trong thời gian chờ đợi",
    }
    occ_duty = occ_duty_map.get(occupation, "hoàn thành tốt công việc và trách nhiệm hàng ngày")
    duty_parts.append(occ_duty)

    return "Có bổn phận " + " và ".join(duty_parts) + "."


def _infer_desire(career_goals: str) -> str:
    """
    Mong muốn — lấy trực tiếp từ career_goals_and_ambitions.
    Đây là trường đã chứa nguyện vọng của person, không cần suy diễn thêm.
    Chỉ cần chuẩn hóa thành 1–2 câu.
    """
    sentences = [s.strip() for s in career_goals.split(".") if s.strip()]
    desire = ". ".join(sentences[:2])
    if not desire.endswith("."):
        desire += "."
    return desire


def _infer_belief(persona: str, cultural_background: str, occupation: str, age: int) -> str:
    """
    Niềm tin — suy từ persona + cultural_background.
    Phản ánh điều person tin rằng mình có thể làm được hoặc đạt được.
    """
    # Lấy câu đầu của persona làm nền tảng
    persona_first = persona.split(".")[0].strip()

    # Xây dựng niềm tin dựa trên giai đoạn cuộc sống và nghề nghiệp
    if age >= 65:
        belief_base = "tin rằng mình vẫn có thể sống vui vẻ, có ích và hòa nhập với cộng đồng dù đã lớn tuổi"
    elif age >= 50:
        belief_base = "tin rằng kinh nghiệm tích lũy nhiều năm là nền tảng để tiếp tục phát triển và đóng góp"
    elif age >= 30:
        belief_base = "tin rằng nỗ lực và kinh nghiệm hiện tại đủ để đạt được mục tiêu đã đặt ra"
    else:
        belief_base = "tin rằng bản thân còn nhiều cơ hội và khả năng để phát triển và khẳng định bản thân"

    # Bổ sung từ cultural_background nếu có từ khóa gợi ý niềm tin cộng đồng
    community_signals = ["cộng đồng", "xóm giềng", "làng", "gia đình", "truyền thống"]
    cultural_text = cultural_background.lower()
    if any(s in cultural_text for s in community_signals):
        belief_suffix = ", đặc biệt khi có sự hỗ trợ từ gia đình và cộng đồng xung quanh"
    else:
        belief_suffix = ""

    return f"{belief_base.capitalize()}{belief_suffix}."


def build_fantasy_world(row: dict) -> dict:
    """
    Xây dựng thế giới giả tưởng từ career_goals, persona, cultural_background,
    occupation, marital_status, age.
    Trả về dict gồm 3 chiều: Bổn phận, Mong muốn, Niềm tin.
    """
    duty   = _infer_duty(row["occupation"], row["marital_status"], row["age"])
    desire = _infer_desire(row["career_goals_and_ambitions"])
    belief = _infer_belief(
        row["persona"], row["cultural_background"],
        row["occupation"], row["age"]
    )

    return {
        "Bổn phận":  duty,
        "Mong muốn": desire,
        "Niềm tin":  belief,
    }


# ── HÀM TỔNG HỢP ─────────────────────────────────────────────────────────────

def build_worlds(row: dict) -> dict:
    """
    Đầu vào: dict chứa các trường của một person từ CSV.
    Đầu ra: dict gồm 2 thế giới.
    """
    return {
        "xac_nhan": build_confirmation_world(row),
        "gia_tuong": build_fantasy_world(row),
    }


# ── TEST ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pandas as pd
    import json

    df = pd.read_csv("/mnt/user-data/uploads/sample50.csv")

    for i in [2, 5, 15]:
        row = df.iloc[i].to_dict()
        worlds = build_worlds(row)
        print(f"\n{'='*60}")
        print(f"Person {i}: {row['persona'][:60]}...")
        print("\n--- THẾ GIỚI XÁC NHẬN ---")
        print(worlds["xac_nhan"]["statement"])
        print("\n--- THẾ GIỚI GIẢ TƯỞNG ---")
        for k, v in worlds["gia_tuong"].items():
            print(f"{k}: {v}")