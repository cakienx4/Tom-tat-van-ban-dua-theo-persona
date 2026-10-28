# Ontology-Driven Multi-Document Summarization with Personas Vietnam
## Sử dụng ontology tóm tắt đa văn bản theo nhân khẩu học Việt Nam

---

## 1. Giới thiệu

**Summarize with Personas** là hệ thống tóm tắt văn bản tiếng Việt cá nhân hóa theo persona (nhân khẩu học). Ý tưởng cốt lõi: **cùng một nội dung nguồn, mỗi người thuộc những lĩnh vực khác nhau khi đọc cần những bản tóm tắt khác nhau**, tùy vào ngành nghề, chuyên môn, và mối quan tâm hiện tại của họ — thay vì một bản tóm tắt chung chung cho tất cả.

Hệ thống dựa trên ontology để mô hình hóa persona và dùng LLM (gemini-3.1-flash-lite / gpt-oss-120b) để sinh bản tóm tắt cá nhân hóa, sau đó tự đánh giá chất lượng bằng chính LLM đóng vai giám khảo (LLM-as-judge).

### Hai giả thuyết nghiên cứu chính

1. **H1 — Chọn lọc theo mối quan tâm**: Khi một bản tóm tắt được cá nhân hóa đúng cách, các chủ đề khớp với mối quan tâm/chuyên môn của persona sẽ được dành nhiều không gian, chi tiết hơn so với bản tóm tắt trung lập (không cá nhân hóa).
2. **H2 — Điều chỉnh văn phong theo chuyên môn**: Nội dung khớp đúng lĩnh vực chuyên môn của persona sẽ được tóm tắt theo văn phong chuyên gia (thuật ngữ chuyên ngành, cấu trúc chuyên nghiệp), trong khi nội dung ngoài chuyên môn sẽ được diễn giải bằng ngôn ngữ phổ thông, dễ hiểu.

### Hai pipeline song song

| | Pipeline dân sự (Civilian)                                                               | Pipeline cán bộ nhà nước (RSS/State)                                                                                              |
|---|------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| **Trạng thái** | Đã hoàn thiện phần lớn, không phát triển thêm                                            | **Đang phát triển chính**                                                                                                         |
| **Dữ liệu persona** | `sample50.csv` — hồ sơ suy luận từ ontology                                              | `state_profiles.json` là file gốc, kết quả thực tế đang chạy trên `state_profiles_nt_nn_tc_kn_cd_ch.json`, 12 `nganh_to` (ngành/tổ) |
| **Ontology** | `ontology/persona_analysis_3.obo/.ttl`                                                   | `ontology/persona_states.ttl`                                                                                                     |
| **Đặc trưng** | Phân loại trường HARD/SOFT/GENERAL, phát hiện cộng đồng 5 chiều, suy luận "hai thế giới" | 3 nhánh nội dung song song (xem bên dưới)                                                                                         |

Phần còn lại của README tập trung vào **pipeline RSS**, vì đây là hướng phát triển chính.

### Ba nhánh nội dung của pipeline RSS

| Nhánh | Nguồn dữ liệu | Mô tả                                                                          |
|---|---|--------------------------------------------------------------------------------|
| **Báo chí** (`baochi`) | RSS VNExpress | Tóm tắt tin tức cá nhân hóa theo chủ đề                                        |
| **Hành chính** (`hanhchinh`) | Văn bản hành chính hanoi.gov.vn (.docx) | Tóm tắt văn bản theo tầng độ sâu phù hợp với vai trò cán bộ                    |
| **Chính luận** (`chinhluan`) | nhandan.vn (Xã luận + Bình luận - Phê phán) | Tóm tắt giữ nguyên cấu trúc lập luận (Vấn đề → Luận điểm → Luận cứ → Kết luận) |

---

## 2. Kiến trúc tổng quan

Toàn bộ pipeline gồm 4 bước, lặp lại cho cả 3 nhánh nội dung:

```
Persona (state_profiles.json)          Nguồn nội dung (RSS / docx / nhandan)
              │                                        │
              ▼                                        ▼
      Ontology query (persona_states.ttl)      Extract + chuẩn hóa
              │                                        │
              └──────────────┬─────────────────────────┘
                              ▼
                   Ontology context + prompt LLM
                              │
                              ▼
                   Bản tóm tắt cá nhân hóa
                              │
                              ▼
                Đánh giá (LLM-as-judge, 6 tiêu chí)
                              │
                              ▼
                 output/dataset/{nhanh}/{variant}.jsonl
                    (dữ liệu SFT để fine-tune)
```

**2 tiên đề cốt lõi chi phối toàn bộ prompt engineering:**

1. Chủ đề khớp mối quan tâm của persona → được dành nhiều không gian hơn trong bản tóm tắt.
2. Nội dung khớp lĩnh vực chuyên môn của persona → tóm tắt theo văn phong chuyên gia (thuật ngữ chuyên ngành, cấu trúc chuyên nghiệp).

**Tiêu chí đánh giá** (bản tóm tắt phải đạt cả 6 mới được coi là hợp lệ để đưa vào tập SFT):
- Báo chí + Hành chính: 6 tiêu chí
1. Chọn lọc phù hợp
2. Nhất quán
3. Trình bày phù hợp
4. Bố cục ưu tiên
5. Giọng điệu phù hợp
6. Thái độ đúng đắn

- Chính luận: 7 tiêu chí:
1. Giữ đúng lập trường, không suy diễn/thiên lệch
2. Đúng trình tự Vấn đề -> Luận điểm -> Luận cứ -> Kết luận
3. Đầy đủ luận điểm cốt lõi, không bỏ sót thông điệp chính
4. Bảo toàn quan hệ lập luận
5. Giữ tính thuyết phục
6. Cá nhân hóa đúng cách (trọng tâm/chi tiết/diễn đạt + mức chuyên môn)
7. Mạch lạc, tự nhiên

---

## 3. Cấu trúc thư mục dự án

```
├── data
│   ├── bao_chi
│   │   ├── vnexpress_rss_snapshot.csv
│   │   └── vnexpress_rss_snapshot.json                  # RSS của vnexpress.net
│   ├── chinh_luan
│   │   ├── nhandan_chinhluan.csv
│   │   └── nhandan_chinhluan.json                            # RSS của nhandan.vn
│   ├── hanh_chinh
│   │   ├── BC-184-2024.docx                                  # Các văn bản hành chính lấy trên hanoi.gov.vn
│   │   ├── ...
│   │   └── TB-1077-2026.docx
│   └── profile                                               # Profile chia theo các biến thể
│       ├── state_profiles_nt.json                            # ngành to
│       ├── state_profiles_nt_nn.json                         # ngành to + ngành nhỏ
│       ├── ...
│       └── state_profiles_nt_nn_tc_kn_cd_ch.json             # đầy đủ các trường
├── output
│   ├── bao_chi            
│   ├── chinh_luan
│   ├── dataset
│   └── hanh_chinh
├── pipeline
│   ├── baochi
│   │   ├── __init__.py
│   │   ├── evaluation_bao_chi.py                           # chấm điểm bản tóm tắt RSS theo 6 tiêu chí (LLM-as-judge)
│   │   ├── fetch_rss_vnexpress.py                          # lấy snapshot RSS từ vnexpress.net
│   │   ├── rss_tom_tat_bai.py                              # vì 1 bài báo có thể được nhiều persona quan tâm, tóm tắt 1 lần rồi dùng lại cho tất cả, tránh gọi LLM lặp lại (dùng bên gpt)
│   │   └── bao_chi_personalize.py                          # lọc + xếp hạng tin theo persona, gọi LLM sinh tóm tắt
│   ├── chinhluan
│   │   ├── __init__.py
│   │   ├── chinh_luan_extract.py                             # trích xuất + tách đoạn bài chính luận từ dữ liệu RSS
│   │   ├── chinh_luan_personalize.py                         # cá nhân hóa độ dài/mức chi tiết theo persona, giữ nguyên mọi luận điểm
│   │   ├── chinh_luan_phan_tich_lap_luan.py                  # phân tích cấu trúc lập luận, KHÔNG phụ thuộc persona (persona-agnostic)
│   │   ├── evaluation_chinh_luan.py                          # chấm điểm theo 7 tiêu chí (thêm tiêu chí bảo toàn quan hệ lập luận)
│   │   └── fetch_rss_nhandan.py                              # lấy dữ liệu Xã luận + Bình luận - Phê phán từ nhandan.vn
│   ├── datasets
│   │   ├── __init__.py
│   │   ├── build_dataset.py                                # gom các bản tóm tắt thành sample dạng hội thoại (system, user, assistant) và ghi ra file jsonl theo từng nhánh và từng variant persona
│   │   ├── dataset_split.py                                # kiểm tra dataset trước khi dùng
│   │   ├── dataset_stats.py                                # chia tập train/val
│   │   └── dataset_validate.py                             # thống kê dataset và ghi ra README.md 
│   ├── hanhchinh
│   │   ├── __init__.py
│   │   ├── evaluation_hanh_chinh.py                          # chấm điểm bản tóm tắt hành chính theo 6 tiêu chí
│   │   ├── hanh_chinh_extract.py                             # trích xuất nội dung + đối tượng thi hành từ file .docx
│   │   ├── hanh_chinh_persona_match.py                       # khớp persona phù hợp theo ngành (gọi LLM để khớp nganh_to/nganh_nho)
│   │   └── hanh_chinh_personalize.py                         # sinh bản tóm tắt cá nhân hóa theo persona đã khớp
│   ├── profiles
│   │   ├── __init__.py
│   │   ├── enrich_state_profiles.py                          # viết lại mo_ta_chung/cau_hoi_truoc_mat bằng LLM (thay bản template)
│   │   ├── generate_profile_variants.py                      # sinh 14 file biến thể trường từ FIELD_ORDER
│   │   ├── generate_state_profiles.py                        # sinh 53 persona gốc theo taxonomy 12 ngành
│   │   └── ontology_context_state.py                         # truy vấn SPARQL trên persona_states.ttl, tạo ngữ cảnh ontology cho prompt
│   ├── __init__.py
│   └── utils.py                                              # các hàm & hằng số dùng chung (gọi LLM, retry, load ontology...)
└── persona_states.ttl                                        # ontology của nhánh RSS/State (khác ontology nhánh dân sự)
```

---

## 4. Cài đặt

### Yêu cầu

- Python 3.10+
- Các thư viện chính: `rdflib`, `pronto`, `httpx`, `openai`, `feedparser`, `python-docx`, `datasets`

### Cấu hình theo từng máy

**Máy chạy gemini** (chạy async):
- Dùng module `pipeline/utils.py`.
- Model sử dụng chính là gemini-3.1-flash-lite (miễn phí qua tài khoản gemini AI)
---

## 5. Cách chạy pipeline

Mọi module chạy dưới dạng package, từ **thư mục gốc project**:

```bash
python -m pipeline.<nhanh>.<module> [tham số]
```

### Sinh và làm giàu persona (chạy 1 lần nếu chưa có dữ liệu trong data)

```bash
# Sinh 53 persona gốc
python -m pipeline.profiles.generate_state_profiles

# Làm giàu mô tả persona bằng LLM (mo_ta_chung, cau_hoi_truoc_mat)
python -m pipeline.profiles.enrich_state_profiles

# Sinh 14 biến thể trường dữ liệu (dùng để huấn luyện mô hình chọn lọc trường phù hợp)
python -m pipeline.profiles.generate_profile_variants
```

### Nhánh Báo chí

```bash
# 1. Tóm tắt cá nhân hóa — test 1 persona trước
python -m pipeline.baochi.bao_chi_personalize --id NN001

# 2. Chạy toàn bộ persona (song song, async)
python -m pipeline.baochi.bao_chi_personalize

# 3. Chạy số lượng persona cho trước (<n> persona)
python -m pipeline.baochi.bao_chi_personalize --so-luong <n>

# 4. Chạy persona theo biến thể (<variants>: nt, nt_nn,...), nếu không có --variant thì mặc định sẽ là biến thể đầy đủ nt_nn_tc_kn_cd_ch
python -m pipeline.baochi.bao_chi_personalize --variant <variants>

# 4. Đánh giá bằng LLM-judge (các parser tương tự trên)
python -m pipeline.baochi.evaluation_bao_chi
```

### Nhánh Hành chính

```bash
# Test 1 persona trên 1 văn bản cụ thể
python -m pipeline.hanhchinh.hanh_chinh_personalize --file ten_van_ban.docx --id NN001

# Chạy <n> persona đầu tiên cho 1 văn bản
python -m pipeline.hanhchinh.hanh_chinh_personalize --file ten_van_ban.docx --so-luong <n>

# Chạy tóm tắt từ id <a> đến id <b>
python -m pipeline.hanhchinh.hanh_chinh_personalize --file ten_van_ban.docx --tu-id <a> --den-id <b>

# Chạy persona theo biến thể (<variants>: nt, nt_nn,...), nếu không có --variant thì mặc định sẽ là biến thể đầy đủ nt_nn_tc_kn_cd_ch
python -m pipeline.hanhchinh.hanh_chinh_personalize --file ten_van_ban.docx --variant <variants> <--id/--so-luong/...>

# Đánh giá
python -m pipeline.hanhchinh.evaluation_hanh_chinh --file ten_van_ban.docx --so-luong 53
```

### Nhánh Chính luận

```bash
# 1. Tách đoạn + phân tích cấu trúc lập luận (persona-agnostic, chạy 1 lần/bài)
python -m pipeline.chinhluan.chinh_luan_phan_tich_lap_luan --id NN001 --bai-id CL0001

# 2. Cá nhân hóa theo persona
python -m pipeline.chinhluan.chinh_luan_personalize --bai-id CL0001 --so-luong 53

# 3. Chạy tóm tắt từ id <a> đến id <b>
python -m pipeline.chinhluan.chinh_luan_personalize --bai-id CL0001 --tu-id <a> --den-id <b>

# 4. Chạy persona theo biến thể (<variants>: nt, nt_nn,...), nếu không có --variant thì mặc định sẽ là biến thể đầy đủ nt_nn_tc_kn_cd_ch
python -m pipeline.hanhchinh.chinh_luan_personalize --bai-id CL0001 --variant <variants> <--id/--so-luong/...>

# 5. Đánh giá theo 7 tiêu chí
python -m pipeline.chinhluan.evaluation_chinh_luan --bai-id CL0001
```

### Tham số dùng chung ở hầu hết module

| Tham số | Ý nghĩa |
|---|---|
| `--id <ID>` | Chỉ chạy 1 persona cụ thể — **luôn test bằng tham số này trước khi chạy batch lớn** |
| `--so-luong N` | Chạy N persona đầu tiên || `--tu-id / --den-id` | Chạy theo khoảng persona |
| `--variant <ten_bien_the>` | Chạy trên 1 trong 14 biến thể trường dữ liệu, kết quả ghi vào thư mục con riêng để không đè lên dữ liệu persona đầy đủ trường |

---

## 6. Build dataset huấn luyện (SFT)

Sau khi đã có kết quả tóm tắt + đánh giá cho cả 3 nhánh:

```bash
python -m pipeline.datasets.build_dataset      # gộp thành output/dataset/{nhanh}/{variant}.jsonl
python -m pipeline.datasets.dataset_validate   # kiểm tra tính hợp lệ
python -m pipeline.datasets.dataset_split      # chia train/val/test
python -m pipeline.datasets.dataset_stats      # xem thống kê số lượng theo nhánh/biến thể
```

Chỉ những bản tóm tắt **đạt cả 6/6 (hoặc 7/7 với chính luận) tiêu chí đánh giá** mới được đưa vào tập dữ liệu huấn luyện cuối cùng.
