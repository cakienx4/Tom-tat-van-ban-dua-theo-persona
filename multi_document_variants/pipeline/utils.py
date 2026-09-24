import re
import time
from rdflib import Graph, Namespace
from pathlib import Path

MAX_RETRY_ATTEMPTS = 5
SUMMARY_MODEL_NAME = "gemini-3.1-flash-lite"

OSS_HOST = "https://text-sum-gpt-oss-120b-runai-text-sum.runai-inference.cyberspace.vn"
OSS_MODEL_NAME = "gpt-oss-120b"

NGANH_TO_SANG_GENRE = {
    "Công chức hành chính nhà nước": ["Chính trị / Pháp luật", "Thời sự / Xã hội"],
    "Quân đội": ["Quốc phòng / An ninh", "Thời sự / Xã hội"],
    "Công an / Cảnh sát": ["Quốc phòng / An ninh", "Chính trị / Pháp luật"],
    "An ninh - Quốc phòng": ["Quốc phòng / An ninh", "Chính trị / Pháp luật"],
    "Ngoại giao": ["Ngoại giao / Quan hệ quốc tế", "Chính trị / Pháp luật"],
    "Tài chính - Ngân sách": ["Tài chính / Kế toán", "Chính trị / Pháp luật"],
    "Ngân hàng - Tiền tệ": ["Tài chính / Kế toán", "Thời sự / Xã hội"],
    "Tư pháp - Pháp luật": ["Chính trị / Pháp luật", "Thời sự / Xã hội"],
    "Y tế": ["Y tế / Chăm sóc", "Thời sự / Xã hội"],
    "Giáo dục - Đào tạo": ["Giáo dục", "Thời sự / Xã hội"],
    "Khoa học - Công nghệ - TT&TT": ["Công nghệ / Kỹ thuật số", "Thời sự / Xã hội"],
    "Nông nghiệp - Tài nguyên - Môi trường": ["Môi trường", "Thời sự / Xã hội"],
}


def lay_chu_de_hieu_luc(persona: dict) -> list:
    if persona.get("chu_de"):
        return persona["chu_de"]
    nganh_to = persona.get("nganh_to", "")
    if nganh_to in NGANH_TO_SANG_GENRE:
        return NGANH_TO_SANG_GENRE[nganh_to]
    return ["Thời sự / Xã hội"]

def retry_generate(func, *args, **kwargs):
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)

        except Exception as e:
            msg = str(e)
            attempt += 1

            if attempt > MAX_RETRY_ATTEMPTS:
                raise RuntimeError(
                    f"Gemini vẫn lỗi sau {MAX_RETRY_ATTEMPTS} lần retry: {msg}"
                ) from e

            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                match = re.search(r"retry in ([0-9.]+)s", msg, re.IGNORECASE)
                wait = float(match.group(1)) + 2 if match else 40
                print(f"\n429 quota. Đợi {wait:.1f}s... (lần {attempt}/{MAX_RETRY_ATTEMPTS})")
                time.sleep(wait)
                continue

            elif "503" in msg or "UNAVAILABLE" in msg:
                wait = 20
                print(f"\nServer bận. Đợi {wait}s... (lần {attempt}/{MAX_RETRY_ATTEMPTS})")
                time.sleep(wait)
                continue

            raise

def load_graph(ttl_path: str) -> Graph:
    g = Graph()
    ttl_path = Path(ttl_path).resolve().as_uri()
    g.parse(ttl_path, format='turtle')
    return g
