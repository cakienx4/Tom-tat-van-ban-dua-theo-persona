"""
community.py
Xác định community của một person dựa trên rule-based logic.
5 chiều: Language, Topic, Domain, Cultural, Prototype
"""

# ── CHIỀU LANGUAGE ──────────────────────────────────────────────────────────

def get_language(education_level: str, age: int) -> dict:
    """
    Suy ra từ education_level (HARD, ưu tiên cao nhất) + age (HARD, bổ trợ).
    Trả về dict gồm level (1-4) và mô tả.
    """
    edu_map = {
        "Không học vấn":        1,
        "Tiểu học":             1,
        "THCS":                 2,
        "THPT":                 2,
        "Trung cấp / Cao đẳng": 3,
        "Đại học":              3,
        "Sau đại học":          4,
    }
    level = edu_map.get(education_level, 2)

    # Bổ trợ: người trên 70 tuổi điều chỉnh xuống 1 bậc (CQ3)
    if age >= 70 and level > 1:
        level -= 1

    desc_map = {
        1: "Đơn giản — câu ngắn, từ ngữ đời thường, không dùng thuật ngữ chuyên môn",
        2: "Trung bình — câu rõ ràng, hạn chế thuật ngữ, ví dụ cụ thể",
        3: "Trung bình-cao — có thể dùng thuật ngữ phổ thông, lập luận 2 tầng",
        4: "Phức tạp — thuật ngữ chuyên môn, lập luận nhiều tầng, số liệu chi tiết",
    }
    return {"level": level, "description": desc_map[level]}


# ── CHIỀU TOPIC ──────────────────────────────────────────────────────────────

def get_topic(occupation: str, age: int) -> list:
    """
    Suy ra từ occupation (HARD) + age (HARD, bổ trợ cho người nghỉ hưu/cao tuổi).
    Trả về list các chủ đề ưu tiên theo thứ tự giảm dần.
    """
    occupation_map = {
        "Buôn bán / kinh doanh":              ["Thị trường", "Giá cả", "Kinh doanh", "Tài chính"],
        "Kỹ thuật viên / kỹ sư":              ["Kỹ thuật", "Công nghệ", "Khoa học"],
        "Nghỉ hưu":                           ["Sức khỏe", "Đời sống", "Gia đình", "Cộng đồng"],
        "Nông nghiệp / ngư nghiệp":           ["Nông sản", "Thời tiết", "Địa phương", "Môi trường"],
        "Y tế / dược":                        ["Sức khỏe", "Y học", "Dinh dưỡng"],
        "Nghiên cứu / học thuật":             ["Tri thức", "Phân tích", "Giáo dục", "Khoa học"],
        "Công nhân / lao động phổ thông":     ["Đời sống", "Thu nhập", "Việc làm", "Thực tế"],
        "Tài xế / giao hàng":                ["Giao thông", "Đời sống", "Thu nhập"],
        "Xây dựng / thợ thủ công":           ["Xây dựng", "Vật liệu", "Thực hành"],
        "Nhân viên văn phòng":               ["Công việc", "Kỹ năng mềm", "Tài chính cá nhân"],
        "Freelancer / làm tự do":            ["Sáng tạo", "Công nghệ", "Kinh doanh cá nhân"],
        "Quản lý / kinh doanh":              ["Quản lý", "Kinh doanh", "Lãnh đạo", "Thị trường"],
        "Dịch vụ / phục vụ":                ["Đời sống", "Kỹ năng giao tiếp", "Du lịch"],
        "Thất nghiệp / tìm việc":           ["Việc làm", "Kỹ năng", "Tài chính cá nhân"],
        "Nghề tự do online / sáng tạo nội dung": ["Sáng tạo", "Công nghệ", "Truyền thông"],
        "Khác / không rõ":                   ["Đời sống", "Thực tế", "Cộng đồng"],
    }
    topics = occupation_map.get(occupation, ["Đời sống", "Thực tế"])

    # Bổ trợ: người >= 60 tuổi luôn thêm "Sức khỏe" vào đầu nếu chưa có (CQ3)
    if age >= 60 and "Sức khỏe" not in topics:
        topics = ["Sức khỏe"] + topics

    return topics


# ── CHIỀU DOMAIN ─────────────────────────────────────────────────────────────

def get_domain(skills_and_expertise: str, occupation: str) -> list:
    """
    Suy ra từ skills_and_expertise văn xuôi (HARD) + occupation (HARD).
    Trả về list các lĩnh vực chuyên môn thực sự của person.
    Dùng để lược bỏ nội dung nhập môn trong lĩnh vực đã thành thạo (CQ8).
    """
    skills_text = skills_and_expertise.lower()

    # Ánh xạ keyword trong skill sang domain
    domain_keywords = {
        "Công nghệ / Kỹ thuật số": [
            "máy tính", "lập trình", "phần mềm", "website", "công nghệ",
            "GPS", "kỹ thuật số", "giao diện", "tối ưu", "thiết kế đồ họa"
        ],
        "Tài chính / Kế toán": [
            "tài chính", "kế toán", "lợi nhuận", "ngân sách", "đầu tư", "tính toán"
        ],
        "Quản lý / Tổ chức": [
            "quản lý", "tổ chức", "lãnh đạo", "dự án", "kế hoạch", "điều phối"
        ],
        "Giao tiếp / Truyền thông": [
            "giao tiếp", "thuyết trình", "đàm phán", "quan hệ", "truyền thông"
        ],
        "Nấu ăn / Ẩm thực": [
            "nấu ăn", "ẩm thực", "chế biến", "món ăn", "dinh dưỡng"
        ],
        "Thủ công / Nghề truyền thống": [
            "thủ công", "nghề truyền thống", "tháo lắp", "bảo dưỡng", "sửa chữa"
        ],
        "Vận tải / Giao nhận": [
            "lái xe", "điều khiển", "giao hàng", "vận chuyển", "bản đồ"
        ],
        "Nông nghiệp / Tự nhiên": [
            "trồng", "chăm sóc vườn", "nông nghiệp", "nuôi", "thu hoạch"
        ],
        "Y tế / Chăm sóc": [
            "y tế", "chăm sóc", "sức khỏe", "bệnh", "dược"
        ],
        "Sáng tạo / Nghệ thuật": [
            "sáng tạo", "thiết kế", "nghệ thuật", "âm nhạc", "phác thảo"
        ],
    }

    domains = set()

    for domain, keywords in domain_keywords.items():
        if any(kw in skills_text for kw in keywords):
            domains.add(domain)

    # Fallback từ occupation nếu không xác định được từ skills
    if not domains:
        occ_domain_map = {
            "Buôn bán / kinh doanh":          ["Tài chính / Kế toán", "Quản lý / Tổ chức"],
            "Kỹ thuật viên / kỹ sư":          ["Công nghệ / Kỹ thuật số"],
            "Y tế / dược":                    ["Y tế / Chăm sóc"],
            "Nghiên cứu / học thuật":         ["Quản lý / Tổ chức", "Giao tiếp / Truyền thông"],
            "Freelancer / làm tự do":         ["Sáng tạo / Nghệ thuật", "Công nghệ / Kỹ thuật số"],
            "Tài xế / giao hàng":             ["Vận tải / Giao nhận"],
            "Nông nghiệp / ngư nghiệp":       ["Nông nghiệp / Tự nhiên"],
        }
        domains = set(occ_domain_map.get(occupation, ["Đời sống thực tế"]))

    return sorted(domains)


# ── CHIỀU CULTURAL ────────────────────────────────────────────────────────────

def get_cultural(cultural_background: str, region: str, zone: str) -> dict:
    """
    Suy ra từ cultural_background (GENERAL) + region + zone (GENERAL).
    Trả về dict gồm orientation và context.
    """
    text = cultural_background.lower()

    # Tín hiệu gắn bó truyền thống
    traditional_signals = [
        "truyền thống", "lễ hội", "phong tục", "tập quán", "bài chòi",
        "quan họ", "hát xẩm", "làng", "tổ tiên", "tín ngưỡng", "đình làng"
    ]
    # Tín hiệu cởi mở văn hóa bên ngoài
    open_signals = [
        "quốc tế", "hiện đại", "đa văn hóa", "nước ngoài", "toàn cầu",
        "hội nhập", "công nghệ", "startup", "mạng xã hội"
    ]

    trad_score = sum(1 for s in traditional_signals if s in text)
    open_score = sum(1 for s in open_signals if s in text)

    if trad_score > open_score:
        orientation = "Truyền thống"
    elif open_score > trad_score:
        orientation = "Cởi mở / Hội nhập"
    else:
        orientation = "Trung dung"

    # Zone bổ trợ
    if zone == "Nông Thôn" and orientation == "Trung dung":
        orientation = "Truyền thống"

    return {
        "orientation": orientation,
        "region": region,
        "zone": zone,
        "context": f"{orientation} — {zone} — {region}"
    }


# ── CHIỀU PROTOTYPE ───────────────────────────────────────────────────────────

def get_prototype(row: dict, language: dict, topic: list, cultural: dict) -> str:
    """
    Tổng hợp từ tất cả chiều — mô tả ngắn hình mẫu đại diện.
    """
    age = row["age"]
    sex = row["sex"]
    edu = row["education_level"]
    occ = row["occupation"]
    zone = row["zone"]

    # Xác định giai đoạn cuộc sống
    if age < 30:
        life_stage = "người trẻ"
    elif age < 50:
        life_stage = "người trung niên"
    elif age < 65:
        life_stage = "người lớn tuổi"
    else:
        life_stage = "người cao tuổi"

    prototype = (
        f"{life_stage} {sex.lower()}, {occ.lower()}, trình độ {edu.lower()}, "
        f"sống tại {zone.lower()} {cultural['region']}. "
        f"Văn phong phù hợp: {language['description']}. "
        f"Chủ đề quan tâm chính: {', '.join(topic[:3])}. "
        f"Định hướng văn hóa: {cultural['orientation']}."
    )
    return prototype


# ── HÀM TỔNG HỢP ─────────────────────────────────────────────────────────────

def determine_community(row: dict) -> dict:
    """
    Đầu vào: dict chứa các trường của một person từ CSV.
    Đầu ra: dict community với 5 chiều.
    """
    language = get_language(row["education_level"], row["age"])
    topic    = get_topic(row["occupation"], row["age"])
    domain   = get_domain(row["skills_and_expertise"], row["occupation"])
    cultural = get_cultural(
        row["cultural_background"], row["region"], row["zone"]
    )
    prototype = get_prototype(row, language, topic, cultural)

    return {
        "Language":  language,
        "Topic":     topic,
        "Domain":    domain,
        "Cultural":  cultural,
        "Prototype": prototype,
    }


# ── TEST ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pandas as pd
    import json

    df = pd.read_csv("/mnt/user-data/uploads/sample50.csv")

    for i in [2, 5, 15]:  # bà Nga, người buôn bán, freelancer
        row = df.iloc[i].to_dict()
        community = determine_community(row)
        print(f"\n{'='*60}")
        print(f"Person {i}: {row['persona'][:60]}...")
        print(json.dumps(community, ensure_ascii=False, indent=2))