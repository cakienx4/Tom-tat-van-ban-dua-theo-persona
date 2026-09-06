"""
ontology_context.py
Query TTL để lấy ontology_context phù hợp với từng person.
Chiến lược: query theo nhánh tương ứng với trường dữ liệu HARD/GENERAL của person.
Mỗi nhánh lấy L1 + quan hệ giữa các term để Gemini hiểu cấu trúc persona.
"""

from rdflib import Graph, Namespace, OWL

BASE = Namespace("http://purl.obolibrary.org/obo/persona#")

# Nhánh HARD và GENERAL — luôn query
HARD_BRANCHES = ["professional_persona", "skills_and_expertise"]
GENERAL_BRANCHES = ["persona", "cultural_background", "career_goals_and_ambitions"]

# Tên hiển thị tiếng Việt cho từng nhánh
BRANCH_LABELS = {
    "professional_persona":       "Hồ sơ nghề nghiệp",
    "skills_and_expertise":       "Kỹ năng và chuyên môn",
    "persona":                    "Bản sắc cá nhân",
    "cultural_background":        "Nền tảng văn hóa",
    "career_goals_and_ambitions": "Mục tiêu và tham vọng",
}

# Tên hiển thị tiếng Việt cho từng loại quan hệ
REL_LABELS = {
    "dinh_hinh":  "định hình",
    "tac_dong":   "tác động đến",
    "cung_co":    "củng cố",
    "thuc_day":   "thúc đẩy",
    "tuong_quan": "tương quan với",
    "uu_tien_hon":"ưu tiên hơn",
}


def load_graph(ttl_path: str) -> Graph:
    g = Graph()
    g.parse(ttl_path, format='turtle')
    return g


def _query_branch(g: Graph, branch: str) -> dict:
    """
    Lấy các term L1 và quan hệ của chúng trong một nhánh.
    Trả về dict: {term_label: [(rel_type, target_label), ...]}
    """
    # Lấy term L1 (con trực tiếp của nhánh)
    q_l1 = f"""
    PREFIX persona: <http://purl.obolibrary.org/obo/persona#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>

    SELECT ?term ?label WHERE {{
        ?term a owl:Class ;
              rdfs:label ?label ;
              rdfs:subClassOf persona:{branch} .
    }}
    """
    l1_terms = {str(r.term): str(r.label) for r in g.query(q_l1)}

    # Lấy quan hệ giữa các term L1 và các term khác trong ontology
    q_rels = f"""
    PREFIX persona: <http://purl.obolibrary.org/obo/persona#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>

    SELECT ?from_uri ?from_label ?rel_uri ?to_label WHERE {{
        ?from_uri rdfs:subClassOf persona:{branch} ;
                  rdfs:label ?from_label .
        ?rel_uri a owl:ObjectProperty .
        ?from_uri ?rel_uri ?to .
        ?to rdfs:label ?to_label .
    }}
    """
    result = {}
    for r in g.query(q_rels):
        from_label = str(r.from_label)
        rel_id     = str(r.rel_uri).split("#")[-1]
        to_label   = str(r.to_label)
        rel_display = REL_LABELS.get(rel_id, rel_id)

        result.setdefault(from_label, []).append((rel_display, to_label))

    # Thêm term L1 không có quan hệ nào
    for label in l1_terms.values():
        result.setdefault(label, [])

    return result


def _format_branch(branch_name: str, branch_data: dict) -> str:
    """
    Chuyển kết quả query một nhánh thành đoạn text cho prompt.
    """
    display_name = BRANCH_LABELS.get(branch_name, branch_name)
    lines = [f"[{display_name}]"]

    for term_label, rels in branch_data.items():
        if rels:
            rel_strs = "; ".join(f"{rel} '{target}'" for rel, target in rels)
            lines.append(f"  • {term_label}: {rel_strs}")
        else:
            lines.append(f"  • {term_label}")

    return "\n".join(lines)


def build_ontology_context(g: Graph) -> str:
    """
    Đầu vào: rdflib Graph đã load TTL.
    Đầu ra: chuỗi ontology_context ghép từ các nhánh HARD + GENERAL.
    """
    sections = []

    for branch in HARD_BRANCHES + GENERAL_BRANCHES:
        branch_data = _query_branch(g, branch)
        if branch_data:
            sections.append(_format_branch(branch, branch_data))

    context = "\n\n".join(sections)
    return context


# ── TEST ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    g = load_graph("/home/claude/persona_analysis_2.ttl")
    context = build_ontology_context(g)
    print(context)
    print(f"\n--- Tổng độ dài context: {len(context)} ký tự ---")