import json
import os

def get_language(education_level: str, age: int) -> dict:
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


def get_topic(occupation: str, age: int) -> list:
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

_DOMAIN_KEYWORDS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "domain_keywords.json"
)

with open(_DOMAIN_KEYWORDS_PATH, encoding="utf-8") as f:
    _DOMAIN_DATA = json.load(f)

DOMAIN_KEYWORDS   = _DOMAIN_DATA["domains"]
KEYWORD_RELATIONS = _DOMAIN_DATA.get("keyword_relations", [])
DOMAIN_PRIORITY   = _DOMAIN_DATA.get("domain_priority", [])

DOMAIN_SCORE_THRESHOLD = 0.6   # ngưỡng để 1 domain được coi là "có liên quan"
PRIORITY_TIE_MARGIN    = 0.15  # chênh lệch điểm coi là "gần bằng nhau" khi tie-break


def _compute_domain_scores(skills_text: str) -> dict:
    """
    Tính điểm từng domain:
    1. Cộng trọng số keyword khớp trực tiếp trong domains.
    2. Cộng/trừ điểm bổ sung từ keyword_relations (tuong_quan/keo_theo dương,
       kim_che âm) khi từ khóa 'from' xuất hiện trong text, tác động lên domain 'to'.
    """
    scores = {domain: 0.0 for domain in DOMAIN_KEYWORDS}

    for domain, keyword_weights in DOMAIN_KEYWORDS.items():
        for kw, weight in keyword_weights.items():
            if kw in skills_text:
                scores[domain] += weight

    for rel in KEYWORD_RELATIONS:
        kw = rel["from"]
        target_domain = rel["to"]
        weight = rel["weight"]
        if kw in skills_text and target_domain in scores:
            scores[target_domain] += weight

    return scores


def _apply_domain_priority(selected: set, scores: dict) -> set:
    """
    Khi 2 domain xung đột (theo domain_priority) đều đã vượt threshold và điểm
    số gần bằng nhau (chênh lệch <= PRIORITY_TIE_MARGIN), chỉ giữ lại domain
    được ưu tiên ('prefer'), loại domain còn lại ('over').
    """
    result = set(selected)
    for rule in DOMAIN_PRIORITY:
        prefer, over = rule["prefer"], rule["over"]
        if prefer in result and over in result:
            diff = abs(scores.get(prefer, 0.0) - scores.get(over, 0.0))
            if diff <= PRIORITY_TIE_MARGIN:
                result.discard(over)
    return result


def get_domain(skills_and_expertise: str, occupation: str) -> list:
    skills_text = skills_and_expertise.lower()

    scores = _compute_domain_scores(skills_text)
    domains = {d for d, score in scores.items() if score >= DOMAIN_SCORE_THRESHOLD}
    domains = _apply_domain_priority(domains, scores)

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


def get_cultural(cultural_background: str, region: str, zone: str) -> dict:
    text = cultural_background.lower()

    traditional_signals = [
        "truyền thống", "lễ hội", "phong tục", "tập quán", "bài chòi",
        "quan họ", "hát xẩm", "làng", "tổ tiên", "tín ngưỡng", "đình làng"
    ]

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


def get_prototype(row: dict, language: dict, topic: list, cultural: dict) -> str:
    age = row["age"]
    sex = row["sex"]
    edu = row["education_level"]
    occ = row["occupation"]
    zone = row["zone"]

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


if __name__ == "__main__":
    import pandas as pd
    import json

    df = pd.read_csv("../data/sample50.csv")

    for i in [2, 5, 15]:  # bà Nga, người buôn bán, freelancer
        row = df.iloc[i].to_dict()
        community = determine_community(row)
        print(f"\n{'='*60}")
        print(f"Person {i}: {row['persona']}...")
        print(json.dumps(community, ensure_ascii=False, indent=2))
