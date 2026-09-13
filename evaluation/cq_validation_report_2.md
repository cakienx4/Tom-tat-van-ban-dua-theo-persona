# Báo cáo validate Competency Questions (CQ)

Thời gian sinh: 2026-09-13 14:58:22
Model tóm tắt: `gemini-3.1-flash-lite` | Model judge: `gemini-3.1-flash-lite`

## Tổng quan
- Tổng số CQ: 20
- PASS: 16 | FAIL: 4 | UNCLEAR: 0 | ERROR: 0

| CQ | Verdict | Confidence | Trường kiểm tra |
|---|---|---|---|
| CQ1 | FAIL | 0.8 | education_level (HARD) |
| CQ2 | PASS | 0.95 | occupation + professional_persona (HARD) |
| CQ3 | PASS | 1.0 | age (HARD) |
| CQ4 | PASS | 1.0 | zone (SOFT, bổ trợ) |
| CQ5 | PASS | 0.95 | hobbies_and_interests (SOFT) + education_level (HARD) |
| CQ6 | PASS | 0.95 | career_goals_and_ambitions (GENERAL) |
| CQ7 | PASS | 1.0 | marital_status (SOFT) |
| CQ8 | PASS | 1.0 | skills_and_expertise (HARD) |
| CQ9 | PASS | 0.9 | region (GENERAL) |
| CQ10 | FAIL | 0.8 | travel_persona (SOFT) |
| CQ11 | PASS | 1.0 | occupation/professional_persona (HARD) x arts_persona (SOFT) |
| CQ12 | FAIL | 0.9 | sports_persona (SOFT) |
| CQ13 | PASS | 1.0 | sex |
| CQ14 | PASS | 1.0 | country (HARD, cố định) |
| CQ15 | PASS | 1.0 | persona (GENERAL) |
| CQ16 | PASS | 1.0 | cultural_background (GENERAL) |
| CQ17 | PASS | 0.9 | zone + occupation (HARD) vs travel_persona (SOFT) - quan hệ uu_tien_hon |
| CQ18 | FAIL | 0.9 | occupation x zone (HARD x SOFT combo) |
| CQ19 | PASS | 0.95 | arts_persona (SOFT) |
| CQ20 | PASS | 0.9 | hobbies_and_interests (SOFT) |


---
## CQ1: Trình độ học vấn của người dùng có ảnh hưởng đến độ phức tạp ngôn ngữ trong bản tóm tắt không?
**Trường kiểm tra:** education_level (HARD)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Bà Nga dùng câu ngắn, từ ngữ đời thường, không thuật ngữ; tóm tắt cho Oanh có thể dùng câu phức tạp hơn, lập luận nhiều tầng hơn rõ rệt.

### Person A — Bà Nga - Không học vấn, 88 tuổi
```
Lễ hội pháo hoa quốc tế tại Đà Nẵng sẽ diễn ra từ ngày 31/5 đến 12/7 với sự tham gia của 8 đội, trong đó có Việt Nam. Điểm đáng chú ý là khu vực trải nghiệm ẩm thực đường phố và các gian hàng thủ công mỹ nghệ truyền thống được tổ chức ngay tại lễ hội. Vé xem có giá từ 200.000 đến 800.000 đồng. Các du khách từ nơi khác có thể đặt tour trọn gói để thuận tiện đi lại. Vì thời tiết tháng 6 ở Đà Nẵng hay mưa bất chợt, ban tổ chức khuyên mọi người nên đi sớm ít nhất 1 tiếng để đỗ xe, ổn định chỗ ngồi và chuẩn bị áo mưa phòng thân.
```

### Person B — Oanh - Sau đại học, nhà nghiên cứu
```
Lễ hội pháo hoa quốc tế Đà Nẵng (31/5 - 12/7) quy tụ 8 đội quốc tế, bổ sung khu vực trải nghiệm ẩm thực đường phố và gian hàng thủ công mỹ nghệ truyền thống đầy màu sắc. Vé dao động 200.000 - 800.000 đồng tùy vị trí. Các tỉnh thành khác có thêm lựa chọn tour trọn gói. Khán giả lưu ý thời tiết tháng 6 dễ có mưa bất chợt, nên đến sớm để ổn định vị trí. Đối với các điểm đến khác ngoài Đà Nẵng, sự kiện chỉ mang tính chất tham khảo không đáng kể. Sự kiện này hứa hẹn là một trải nghiệm văn hóa đầy sống động, tựa như màn trình diễn ánh sáng rực rỡ giữa bầu trời đêm mùa hạ, khơi gợi xúc cảm về những chuyến viễn du đầy thi vị.
```

### Đánh giá LLM judge
- **Verdict:** FAIL
- **Confidence:** 0.8
- **Lý do:** Bản A (dành cho Bà Nga) vẫn sử dụng cấu trúc câu dài và thông tin chưa được giản lược hóa đủ mức so với đối tượng người già không học vấn. Bản B (dành cho Oanh) lại thêm vào các chi tiết mang tính văn chương, cảm xúc thay vì tăng cường lập luận logic hay độ phức tạp tư duy, khiến sự khác biệt về bản chất giữa hai bản tóm tắt chưa phản ánh đúng kỳ vọng về trình độ học vấn.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ2: Nghề nghiệp và lĩnh vực làm việc của người dùng có quyết định chủ đề văn bản nào được ưu tiên tóm tắt không?
**Trường kiểm tra:** occupation + professional_persona (HARD)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Minh nhấn vào giá vé, chi phí, cơ hội kinh doanh dịch vụ du lịch quanh lễ hội; tóm tắt cho Hiếu có thể trung lập hơn hoặc nhấn khía cạnh khác (không nhất thiết nhấn kinh doanh).

### Person A — Minh - Buôn bán lúa gạo
```
Lễ hội pháo hoa quốc tế tại Đà Nẵng diễn ra từ ngày 31/5 đến 12/7. Sự kiện quy tụ các đội từ nhiều quốc gia như Ý, Úc, Mỹ, Phần Lan và Việt Nam. Điểm đáng chú ý với người thích văn hóa truyền thống là lễ hội có thêm các gian hàng thủ công mỹ nghệ và khu ẩm thực đường phố. Vé xem pháo hoa có giá từ 200.000 đến 800.000 đồng. Ban tổ chức khuyên người xem nên đến sớm để ổn định chỗ ngồi và chuẩn bị áo mưa phòng thời tiết bất chợt. Các thông tin về tour du lịch trọn gói dành cho khách phương xa không phù hợp với nhu cầu của anh.
```

### Person B — Dương Xuân Hiếu - Y tế / dược
```
Lễ hội pháo hoa quốc tế Đà Nẵng dự kiến diễn ra từ 31/5 đến 12/7 với 8 đội tham dự. Ban tổ chức bổ sung khu vực ẩm thực đường phố và gian hàng thủ công mỹ nghệ, vé có giá từ 200.000 đến 800.000 đồng. Du khách từ các địa phương khác có thể đặt tour trọn gói bao gồm vận chuyển và lưu trú. Người xem được khuyến cáo đến trước 1 tiếng để đỗ xe, ổn định chỗ ngồi và chủ động chuẩn bị áo mưa do thời tiết tháng 6 thường có mưa bất chợt. Các điểm đến lịch sử, văn hóa khác tại Đà Nẵng cũng được mở cửa phục vụ du khách trong thời gian này.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 0.95
- **Lý do:** Bản tóm tắt A của Minh được cá nhân hóa bằng cách loại bỏ các thông tin về tour du lịch không phù hợp và tập trung vào các yếu tố có thể ảnh hưởng đến hoạt động buôn bán. Ngược lại, bản B của Hiếu mang tính chất cung cấp thông tin trung lập và bao quát cho du khách, đúng với mục tiêu cá nhân hóa theo nghề nghiệp đã đề ra.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ3: Độ tuổi của người dùng có làm thay đổi chủ đề được nhấn mạnh trong bản tóm tắt không?
**Trường kiểm tra:** age (HARD)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Phương Hạnh (trẻ) có thể nhấn cơ hội/khởi đầu tập luyện cơ bản; tóm tắt cho Bà Nga nhấn mạnh khía cạnh sức khỏe, vận động nhẹ nhàng, an toàn cho người lớn tuổi.

### Person A — Phương Hạnh - 21 tuổi, thất nghiệp tìm việc
```
Để bảo vệ tim mạch, bác sĩ khuyên người trưởng thành cần vận động cường độ vừa ít nhất 150 phút mỗi tuần. Nếu bạn mới bắt đầu tập luyện, hãy khởi động kỹ và chọn các bài nhẹ nhàng như đi bộ hoặc yoga trước khi tăng dần cường độ. Ngoài ra, văn bản cũng đề cập ngắn gọn về các chế độ dinh dưỡng và phương pháp phục hồi chuyên sâu dành cho vận động viên chuyên nghiệp.
```

### Person B — Bà Nga - 88 tuổi, nghỉ hưu
```
Người lớn tuổi nên đi bộ nhẹ nhàng khoảng 150 phút mỗi tuần để khỏe tim mạch, cần khởi động kỹ trước khi tập. Các nội dung về chế độ dinh dưỡng và tập luyện chuyên sâu cho vận động viên không cần quan tâm.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt B đã lược bỏ các yếu tố chuyên sâu không cần thiết và tập trung trực tiếp vào hoạt động đi bộ nhẹ nhàng, phù hợp với nhu cầu an toàn cho người cao tuổi. Ngược lại, bản A duy trì giọng điệu khuyến khích khởi đầu và tăng dần cường độ, phù hợp với đối tượng trẻ tuổi. Sự khác biệt này phản ánh chính xác kỳ vọng về việc cá nhân hóa nội dung theo độ tuổi và tình trạng người dùng.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ4: Khu vực sống (Đô Thị/Nông Thôn) có làm thay đổi phần nào của văn bản được giữ lại trong tóm tắt không?
**Trường kiểm tra:** zone (SOFT, bổ trợ)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Chị Mai (nông thôn) giữ lại phần giá nông sản/kênh phân phối truyền thống; tóm tắt cho Thảo (đô thị) giữ lại phần thương mại điện tử/logistics.

### Person A — Chị Mai - Buôn bán, Nông Thôn, Đà Nẵng
```
Giá lúa gạo Đồng bằng sông Cửu Long đang biến động mạnh do nhu cầu xuất khẩu tăng, tiểu thương nông thôn như tại Đà Nẵng cần theo dõi sát giá thu mua từ các kênh phân phối truyền thống để hạch toán chi tiêu hiệu quả. Trong khi đó, tại các thành phố lớn, xu hướng mua sắm online đang thay đổi mô hình bán lẻ truyền thống. Các biến động giá hàng tiêu dùng nhập khẩu khác chỉ là xu hướng phụ. Bạn nên tận dụng kinh nghiệm quản lý và kỹ năng công nghệ sẵn có để duy trì ổn định hoạt động kinh doanh.
```

### Person B — Phạm Thị Thảo - Buôn bán, Đô Thị, TP.HCM
```
Giá hàng tiêu dùng tại các siêu thị mini đô thị có xu hướng giảm nhẹ nhờ tỷ giá ổn định. Đối với hoạt động kinh doanh tại thành phố lớn, cần đẩy mạnh kênh thương mại điện tử và logistics để cạnh tranh hiệu quả, khi xu hướng người tiêu dùng trẻ ngày càng ưu tiên đặt hàng online, gây áp lực lên mô hình bán lẻ truyền thống. Giá lúa gạo tại đồng bằng sông Cửu Long biến động mạnh do nhu cầu xuất khẩu.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt A dành cho Chị Mai tập trung nhấn mạnh vào giá nông sản và kênh phân phối truyền thống, phù hợp với bối cảnh nông thôn. Bản tóm tắt B dành cho Thảo tập trung vào thương mại điện tử, logistics và xu hướng mua sắm online tại đô thị. Cả hai bản tóm tắt đều phản ánh đúng sự thay đổi nội dung trọng tâm theo mục tiêu cá nhân hóa đã đề ra.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ5: Sở thích cá nhân có đủ để xác định góc độ tóm tắt phù hợp không, hay cần kết hợp với education_level?
**Trường kiểm tra:** hobbies_and_interests (SOFT) + education_level (HARD)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Dù cả hai đều có liên quan đến thể thao trong hồ sơ, văn phong tóm tắt cho A vẫn đơn giản hơn B do chênh lệch education_level, chứng tỏ hobbies không tự quyết định toàn bộ cách diễn đạt.

### Person A — Lê Văn Dung - Công nhân, Trung cấp/Cao đẳng
```
Duy trì ít nhất 150 phút vận động cường độ vừa mỗi tuần là chìa khóa để anh bảo vệ tim mạch, đặc biệt khi tham gia cầu lông hay bóng đá tại TP.HCM. Hãy khởi động kỹ, bắt đầu bằng các bài tập nhẹ nhàng trước khi tăng dần cường độ để đảm bảo sức bền. Đối với những người tập luyện chuyên sâu, việc tối ưu dinh dưỡng và kỹ thuật phục hồi cơ bắp là rất quan trọng để duy trì phong độ dài hạn trên sân cỏ.
```

### Person B — Dương Xuân Hiếu - Y tế/dược, Sau đại học
```
Bác sĩ cần duy trì tối thiểu 150 phút vận động cường độ vừa hàng tuần để bảo vệ sức khỏe tim mạch. Với người mới, nên bắt đầu bằng đi bộ hoặc yoga, khởi động kỹ để tránh chấn thương. Đối với vận động viên chuyên nghiệp, tài liệu lưu ý chế độ dinh dưỡng, tỷ lệ protein-carb và phương pháp phục hồi cơ bắp chuyên sâu nhằm tối ưu hóa hiệu suất luyện tập dài hạn.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 0.95
- **Lý do:** Bản tóm tắt B sử dụng thuật ngữ chuyên môn hóa (tỷ lệ protein-carb, tối ưu hóa hiệu suất) và cấu trúc lập luận chặt chẽ hơn phù hợp với người có trình độ sau đại học. Bản A tập trung vào các lời khuyên thực tiễn, đơn giản và dễ tiếp cận hơn cho đối tượng công nhân, xác nhận rằng education_level đóng vai trò quyết định trong việc định hình văn phong dù cùng chủ đề sở thích.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ6: Mục tiêu nghề nghiệp có làm tăng mức độ ưu tiên của nội dung mang tính định hướng tương lai (xu hướng thị trường, cơ hội đầu tư) trong tóm tắt không?
**Trường kiểm tra:** career_goals_and_ambitions (GENERAL)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Thảo giữ lại phần xu hướng thị trường/thương mại điện tử (cơ hội mở rộng); tóm tắt cho Minh thiên về mô tả hiện trạng giá cả ổn định, ít nhấn cơ hội mở rộng.

### Person A — Trần Thùy Thảo - muốn mở rộng kinh doanh ra quốc tế
```
Giá lúa gạo tại Đồng bằng sông Cửu Long biến động mạnh do nhu cầu xuất khẩu tăng, tiểu thương nông thôn cần theo dõi sát giá thu mua tại các kênh phân phối truyền thống để đảm bảo lợi nhuận. Ngược lại, tại các đô thị lớn, xu hướng mua sắm online đang tạo thách thức cho bán lẻ truyền thống, buộc các cửa hàng phải tối ưu hóa thương mại điện tử và logistics.
```

### Person B — Minh - mong muốn ổn định, ít tham vọng mở rộng
```
Giá lúa gạo tuần qua tăng mạnh do xuất khẩu tốt. Anh nên theo dõi sát giá thu mua tại các kênh truyền thống ở quê mình để kinh doanh hiệu quả. Ngoài ra, hàng tiêu dùng tại các siêu thị đô thị có giá giảm nhẹ. Xu hướng mua sắm online tại thành phố cũng đang thay đổi nhiều, nhưng với việc buôn bán tại nông thôn, anh cứ tập trung vào thế mạnh giao thương truyền thống của mình là ổn.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 0.95
- **Lý do:** Bản tóm tắt A tập trung vào việc tối ưu hóa thương mại điện tử và logistics, trực tiếp hỗ trợ mục tiêu mở rộng kinh doanh của Thảo. Bản tóm tắt B nhấn mạnh sự ổn định, khuyên Minh duy trì kênh truyền thống và không nhấn mạnh vào cơ hội phát triển mới. Sự khác biệt này hoàn toàn phản ánh đúng kỳ vọng về việc cá nhân hóa nội dung theo mục tiêu nghề nghiệp của người dùng.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ7: Tình trạng hôn nhân có làm thay đổi góc độ được nhấn mạnh khi tóm tắt văn bản về gia đình/du lịch không?
**Trường kiểm tra:** marital_status (SOFT)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Hoa (đã kết hôn) nhấn vào điểm đến phù hợp gia đình/trẻ nhỏ; tóm tắt cho Hương (ly thân) nhấn vào trải nghiệm cá nhân/độc lập.

### Person A — Huỳnh Thanh Hoa - Đã kết hôn
```
Thị trường du lịch hè năm nay ghi nhận sự tăng trưởng tích cực với các phân khúc khách hàng đa dạng.

Đối với nhóm khách gia đình, đây là phân khúc chiếm tỷ trọng lớn trong thị trường hè với mức tăng 15%. Các chuyến đi thường kéo dài từ ba đến năm ngày, ưu tiên lựa chọn dịch vụ trọn gói để tối ưu chi phí và đảm bảo sự tiện lợi, thoải mái nhất cho các thành viên, đặc biệt là khi có trẻ nhỏ đi cùng. Những chuyến đi này không chỉ là hành trình khám phá các vùng đất mới, mà còn là khoảng thời gian quý giá để gia đình gắn kết, vun đắp tình cảm và lưu giữ những kỷ niệm đẹp đẽ bên nhau.

Các phân khúc khác như khách công sở, du khách đi một mình, sinh viên và khách quốc tế cũng đang có những bước tăng trưởng đáng kể với nhu cầu và phong cách trải nghiệm riêng biệt.

Du lịch hè năm nay cho thấy sự khởi sắc trên diện rộng, hứa hẹn mang lại những làn gió mới cho ngành lữ hành, đáp ứng mọi nhu cầu từ nghỉ dưỡng gia đình truyền thống đến các loại hình trải nghiệm cá nhân hóa.
```

### Person B — Đỗ Thanh Hương - Ly thân
```
Thị trường du lịch hè năm nay duy trì đà tăng trưởng tích cực với sự phân hóa mạnh mẽ theo từng nhóm đối tượng. 

Đáng chú ý nhất đối với phân khúc khách hàng cá nhân độc lập là xu hướng "du lịch chữa lành" (healing travel) đang tăng trưởng vượt trội 22%. Đây là lựa chọn ưu tiên của những người trưởng thành đang tìm kiếm sự cân bằng sau biến cố, với đặc điểm các hành trình linh hoạt, không bị gò bó bởi lịch trình cứng nhắc. Thay vì các tour trọn gói truyền thống, nhóm này chú trọng vào các trải nghiệm cá nhân chuyên sâu như thiền, yoga, retreat và khám phá chiều sâu văn hóa – lịch sử tại địa phương. Các đơn vị lữ hành đang tập trung thiết kế các sản phẩm tối ưu hóa không gian yên tĩnh và thời gian tự do, tách biệt hoàn toàn khỏi những nhịp độ hành trình dày đặc.

Song song đó, các phân khúc khác bao gồm khách doanh nghiệp, nhóm gia đình và sinh viên chỉ ghi nhận mức tăng trưởng từ 12% đến 18% với các mô hình tour nghỉ dưỡng hoặc trải nghiệm theo nhóm bạn phổ thông. Ngoài ra, lượng khách quốc tế cũng đang trên đà phục hồi khả quan.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt A tập trung sâu vào nhu cầu gia đình và sự tiện lợi cho trẻ nhỏ, phù hợp với profile đã kết hôn. Bản tóm tắt B nhấn mạnh vào xu hướng du lịch chữa lành, linh hoạt và trải nghiệm cá nhân hóa, phản ánh đúng kỳ vọng đối với người đang trong tình trạng ly thân. Sự phân hóa nội dung giữa hai bản tóm tắt hoàn toàn khớp với expected_effect đã đặt ra.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ8: Kỹ năng hiện có của người dùng có tác động loại bỏ phần hướng dẫn cơ bản (nhập môn) trong tóm tắt không?
**Trường kiểm tra:** skills_and_expertise (HARD)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Anh Dũng (thiết kế chuyên sâu) lược bỏ phần hướng dẫn cơ bản (mở phần mềm, công cụ cơ bản), chỉ giữ phần nâng cao (typography, motion design); tóm tắt cho Lê Văn Dung có thể giữ lại nhiều hơn hoặc trình bày khác do không có nền tảng thiết kế.

### Person A — Anh Dũng - Freelance designer nhiều năm kinh nghiệm
```
Xu hướng thiết kế UX/UI năm 2025 tập trung mạnh vào AI, thiết kế tương tác thông minh và cá nhân hóa trải nghiệm. Đối với các dự án freelancer, việc ứng dụng AI để phân tích hành vi, đề xuất giao diện và tự động hóa tối ưu hóa bố cục là giải pháp then chốt.

Ở cấp độ chuyên nghiệp, cần tập trung vào typography động để tăng hiệu quả truyền đạt cảm xúc và tối ưu hóa motion design thông qua các micro-interactions. Cụ thể, việc tinh chỉnh easing curve và timing cần được thực hiện có chủ đích để tạo phản hồi tự nhiên. Đặc biệt, các studio hiện nay đang đẩy mạnh tích hợp animation token vào design system nhằm đảm bảo tính nhất quán và khả năng mở rộng sản phẩm trong quá trình vận hành dự án thực tế.

Đây là giai đoạn giao thoa đòi hỏi designer không chỉ làm chủ công cụ mà còn phải nâng cao chiều sâu kỹ thuật trong tư duy thiết kế. Các xu hướng tại những khu vực khác trên thế giới chỉ mang tính chất tham khảo thêm.
```

### Person B — Lê Văn Dung - Công nhân, kỹ năng cơ bản
```
Năm 2025, lĩnh vực thiết kế giao diện (UX/UI) có những thay đổi lớn nhờ sự hỗ trợ của trí tuệ nhân tạo (AI).

Với người mới tiếp cận, đây là một lĩnh vực kỹ thuật mới cần làm quen từ đầu. Bạn nên bắt đầu bằng việc học sử dụng các phần mềm thiết kế phổ biến như Figma hoặc Sketch. Các bước cơ bản bao gồm: tạo file, làm quen thanh công cụ, vẽ khung sườn (wireframe) và ghi nhớ phím tắt. Sau khi thành thạo các thao tác này, bạn nên thực hành dựng bố cục cơ bản gồm phần đầu trang (header), nội dung chính và chân trang (footer).

Đối với sự vận hành của công nghệ, AI đóng vai trò quan trọng trong việc tự động phân tích hành vi người dùng, từ đó đưa ra các đề xuất về giao diện cá nhân hóa, tối ưu bố cục và hỗ trợ xử lý ngôn ngữ tự nhiên thông qua chatbot.

Về phía các nhà thiết kế chuyên nghiệp, xu hướng hiện nay tập trung vào các kỹ thuật nâng cao như typography động và chuyển động vi mô (micro-interactions) để tăng cảm xúc và độ tự nhiên khi tương tác. Các studio lớn cũng đang áp dụng hệ thống thiết kế đồng bộ để duy trì tính nhất quán khi mở rộng sản phẩm.

Tóm lại, thị trường thiết kế hiện nay đang song song tồn tại giữa việc phổ cập công cụ cho người mới và nâng cao tiêu chuẩn kỹ thuật chuyên sâu.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt A đã lược bỏ hoàn toàn các hướng dẫn nhập môn (phần mềm, cách tạo file, vẽ wireframe) và tập trung trực tiếp vào tư duy kỹ thuật chuyên sâu. Ngược lại, bản tóm tắt B giữ lại đầy đủ hướng dẫn cơ bản dành cho người mới bắt đầu, hoàn toàn khớp với kỳ vọng cá nhân hóa dựa trên trình độ người dùng.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ9: Vùng địa lý cư trú có làm tăng mức độ ưu tiên của nội dung địa phương trong tóm tắt không?
**Trường kiểm tra:** region (GENERAL)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho person A giữ lại phần đồng bằng sông Cửu Long/canh tác thông minh nhiều hơn; tóm tắt cho person B có thể giữ phần miền Trung/Tây Nguyên hoặc trung lập hơn nhưng không loại bỏ hoàn toàn nội dung vùng khác.

### Person A — Cô (Cần Thơ) - Buôn bán, gắn với chợ nổi miền Tây
```
Tại Đồng bằng sông Cửu Long, nông dân đang đẩy mạnh áp dụng các mô hình canh tác thông minh để chủ động ứng phó với tình trạng xâm nhập mặn, đảm bảo hiệu quả sản xuất kinh doanh nông sản. Trong khi đó, các vùng miền khác như miền Trung và Tây Nguyên cũng đang phát triển mô hình nông nghiệp kết hợp du lịch sinh thái.
```

### Person B — Oanh - Hải Phòng, vùng đồng bằng sông Hồng
```
Nông nghiệp Việt Nam đang chuyển dịch mạnh mẽ sang công nghệ cao. Các mô hình canh tác thông minh tại đồng bằng sông Cửu Long giúp thích ứng với biến đổi khí hậu. Đặc biệt, xu hướng phát triển nông nghiệp kết hợp du lịch sinh thái tại miền Trung và Tây Nguyên mở ra những hành trình trải nghiệm đầy cảm hứng, như hơi thở thiên nhiên đánh thức mọi giác quan.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 0.9
- **Lý do:** Bản tóm tắt A đặt trọng tâm vào Đồng bằng sông Cửu Long ngay ở câu mở đầu, phù hợp với người dùng tại Cần Thơ. Bản tóm tắt B có cách tiếp cận cân bằng hơn, đề cập đến nông nghiệp chung toàn quốc và không ưu tiên vùng miền nào một cách đặc biệt, phù hợp với kỳ vọng về sự trung lập cho người dùng ngoài vùng miền Tây.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ10: Phong cách du lịch (travel_persona) có làm thay đổi phần nào của văn bản ẩm thực được giữ lại trong tóm tắt không?
**Trường kiểm tra:** travel_persona (SOFT)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Thảo giữ lại phần ẩm thực đường phố/gánh hàng rong bình dân; tóm tắt cho Hương giữ lại phần nhà hàng fine-dining cao cấp.

### Person A — Trần Thùy Thảo - thích khám phá thiên nhiên/địa phương
```
Ẩm thực đường phố từ gánh hàng rong bình dân đến các quán ăn gia truyền vẫn là điểm nhấn thu hút du khách. Như chiếc bánh xèo vàng ươm, giòn rụm đậm đà tình quê, những món ăn này giữ trọn hồn cốt truyền thống. Trong khi đó, nhà hàng fine-dining hiện đại cũng đang nở rộ tại các đô thị lớn.
```

### Person B — Đỗ Thanh Hương - thích điểm đến lịch sử/văn hóa, fine-dining
```
Tại TP.HCM, ẩm thực đường phố với những món truyền thống thân thuộc vẫn giữ sức hút khó cưỡng, như hương vị hủ tiếu hay cơm tấm đậm đà ký ức. Song hành, các nhà hàng fine-dining hiện đại đang định hình phân khúc cao cấp, tinh tế hóa nguyên liệu bản địa, mở ra không gian trải nghiệm ẩm thực đầy sang trọng.
```

### Đánh giá LLM judge
- **Verdict:** FAIL
- **Confidence:** 0.8
- **Lý do:** Bản tóm tắt A dành cho Thảo đề cập đến cả hai loại hình ẩm thực với sự ưu tiên tương đương, chưa làm rõ sự khác biệt trong việc 'giữ lại' nội dung theo đúng kỳ vọng. Bản B cho Hương có nhấn mạnh đến fine-dining hơn, nhưng sự khác biệt giữa hai bản tóm tắt chưa đủ rõ rệt để phản ánh sự cá nhân hóa theo phong cách du lịch như mô tả trong expected_effect.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ11: Người dùng có nghề nghiệp sáng tạo thì bản tóm tắt về văn hóa nghệ thuật có cần giữ lại phần kỹ thuật chuyên môn không?
**Trường kiểm tra:** occupation/professional_persona (HARD) x arts_persona (SOFT)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Anh Dũng giữ lại phần phân tích kỹ thuật (lớp màu, phối màu, trường phái); tóm tắt cho Lê Văn Dung chỉ giữ phần giới thiệu sự kiện và cảm nhận tổng thể.

### Person A — Anh Dũng - Freelance designer (nghề sáng tạo)
```
Triển lãm mỹ thuật đương đại tại Cần Thơ quy tụ hơn 30 tác phẩm của họa sĩ trẻ. Sự kiện phân tích sâu kỹ thuật sơn dầu lớp (layering), cách phối màu tương phản và ảnh hưởng của trường phái biểu hiện trừu tượng đầy cảm xúc lên các tác phẩm. Những nét vẽ như những thanh âm vang vọng giữa lòng đô thị, khơi gợi cảm hứng sáng tạo mạnh mẽ. Các hoạt động cộng đồng khác chỉ diễn ra ngắn gọn.
```

### Person B — Lê Văn Dung - Công nhân/lao động phổ thông
```
Triển lãm mỹ thuật đương đại tại thành phố quy tụ hơn 30 họa sĩ trẻ, mang đến không gian đầy cảm xúc với những lớp màu sơn dầu chồng lấp đầy ma mị và sự bùng nổ của các mảng màu tương phản. Như những thanh âm trừu tượng ngân vang, tác phẩm dẫn lối tâm hồn người xem vào dòng chảy văn hóa truyền thống. Sự kiện còn có hoạt động vẽ tranh trải nghiệm.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt A dành cho Anh Dũng đã tập trung vào các yếu tố chuyên môn như 'kỹ thuật sơn dầu lớp', 'phối màu tương phản' và 'trường phái biểu hiện trừu tượng', đúng với kỳ vọng cho người làm nghề sáng tạo. Bản tóm tắt B của Lê Văn Dung đã lược bỏ các phân tích chuyên môn phức tạp để tập trung vào cảm nhận tổng thể và mô tả dễ hiểu, phù hợp với yêu cầu cá nhân hóa.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ12: Mức độ tham gia thể thao có quyết định phần nào của văn bản sức khỏe được ưu tiên trong tóm tắt không?
**Trường kiểm tra:** sports_persona (SOFT)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Phương Chi có thể giữ phần dinh dưỡng thể thao/phục hồi cơ chuyên sâu hơn; tóm tắt cho Bà Nga giữ phần khuyến nghị sức khỏe cơ bản, vận động nhẹ.

### Person A — Phương Chi - năng động, tập bóng bàn/đi bộ thường xuyên
```
Để bảo vệ tim mạch, người trưởng thành cần duy trì tối thiểu 150 phút vận động cường độ vừa mỗi tuần. Đối với người mới, hãy khởi động kỹ và bắt đầu với đi bộ hoặc yoga nhẹ nhàng. Các hoạt động thể thao khác tại các khu vực ngoài Hà Nội không được đề cập chi tiết. Việc duy trì thói quen vận động như đi bộ không chỉ là bài tập đơn thuần, mà là nhịp điệu hồi sinh, khơi nguồn sức sống bền bỉ cho cơ thể mỗi ngày.
```

### Person B — Bà Nga - chỉ tập nhẹ nhàng, dưỡng sinh
```
Để khỏe mạnh, bà cần đi bộ nhẹ nhàng hoặc vận động mỗi ngày, khoảng 150 phút mỗi tuần là tốt cho tim mạch. Trước khi tập, bà nhớ khởi động kỹ cơ thể để tránh đau nhức. Người tập luyện chuyên nghiệp thì có chế độ ăn uống và phục hồi cơ bắp phức tạp hơn.
```

### Đánh giá LLM judge
- **Verdict:** FAIL
- **Confidence:** 0.9
- **Lý do:** Hai bản tóm tắt chưa thể hiện đúng định hướng cá nhân hóa. Bản A (cho Phương Chi) lại tập trung vào các khuyến nghị cơ bản thay vì chuyên sâu về dinh dưỡng/phục hồi, trong khi bản B (cho Bà Nga) lại đưa thêm nội dung về tập luyện chuyên nghiệp không phù hợp với đối tượng này.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ13: Giới tính có làm thay đổi góc độ ưu tiên trong tóm tắt khi văn bản đề cập đến nhiều nhóm đối tượng không?
**Trường kiểm tra:** sex
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Hải giữ lại phần khuyến nghị dành cho nam giới (tim mạch, tuyến tiền liệt); tóm tắt cho Linh giữ lại phần dành cho nữ giới (xương khớp, tầm soát ung thư vú).

### Person A — Trần Văn Hải - Nam, 48 tuổi
```
Anh Hải ở tuổi 48, cần đặc biệt lưu ý tầm soát định kỳ về tim mạch và tuyến tiền liệt để đảm bảo sức khỏe. Ngoài việc khám tổng quát mỗi năm một lần, anh hãy chú ý duy trì chế độ ăn uống khoa học. Các khuyến nghị sức khỏe cho nữ giới chỉ mang tính tham khảo sơ lược.
```

### Person B — Chị Linh - Nữ, 45 tuổi
```
Ở tuổi trung niên, chị cần chú ý tầm soát sức khỏe xương khớp và ung thư vú định kỳ. Chị nên duy trì chế độ ăn uống cân bằng, khoa học và thực hiện khám sức khỏe tổng quát mỗi năm một lần để đảm bảo sức khỏe ổn định. Nam giới trung niên cũng cần tầm soát bệnh lý tim mạch.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt A tập trung cụ thể vào các khuyến nghị cho nam giới (tim mạch, tuyến tiền liệt) và loại bỏ thông tin không liên quan. Bản tóm tắt B ưu tiên các khuyến nghị cho nữ giới (xương khớp, ung thư vú), đáp ứng đúng kỳ vọng về việc cá nhân hóa nội dung sức khỏe dựa trên giới tính.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ14: Quốc gia cư trú (cố định Việt Nam) có đóng vai trò ràng buộc cứng loại bỏ/chú thích nội dung không phù hợp ngữ cảnh Việt Nam trong tóm tắt không?
**Trường kiểm tra:** country (HARD, cố định)
**Loại test:** single_constraint
**Kỳ vọng (expected_effect):** Bản tóm tắt không trình bày chính sách thuế EU hoặc luật California như thể áp dụng trực tiếp cho người đọc tại Việt Nam; nội dung nước ngoài bị lược bỏ hoặc được chú thích rõ là không áp dụng trực tiếp.

### Person A — Trần Thùy Thảo - dùng làm đại diện chung
```
Chính sách thuế nhập khẩu mới của EU từ quý tới sẽ ảnh hưởng gián tiếp đến hoạt động xuất khẩu nông sản của các doanh nghiệp Việt Nam. Lưu ý, các quy định này tại EU và luật dữ liệu cá nhân tại bang California (Mỹ) không áp dụng trực tiếp cho hoạt động kinh doanh tại địa phương của bạn, chỉ mang tính chất tham khảo. Bạn nên rà soát lại các quy trình vận hành và quản lý.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt đã thực hiện tốt việc chú thích rõ ràng rằng các chính sách của EU và luật tại bang California không áp dụng trực tiếp cho người đọc tại Việt Nam. Nội dung được trình bày dưới góc độ tham khảo và chỉ rõ tác động gián tiếp, hoàn toàn đáp ứng kỳ vọng của hệ thống về tính cá nhân hóa theo quốc gia cư trú.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ15: Giá trị sống và thế giới quan (persona) có ảnh hưởng đến văn phong và ngữ điệu của bản tóm tắt không?
**Trường kiểm tra:** persona (GENERAL)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Hương súc tích, thiên về số liệu/kết luận rõ ràng; tóm tắt cho Bà Nga có thể nhẹ nhàng, gần gũi đời thường hơn.

### Person A — Đỗ Thanh Hương - quản lý, thực dụng, tham vọng
```
Thị trường lao động đang chuyển dịch mạnh mẽ với xu hướng làm việc từ xa để cân bằng cuộc sống. Đối với quản lý, việc duy trì hiệu suất công việc và đạt mục tiêu tăng trưởng kinh doanh là ưu tiên cốt lõi, song song với kế hoạch ổn định lại cuộc sống cá nhân sau ly thân.
```

### Person B — Bà Nga - tận hưởng tuổi già, bình yên
```
Nhiều người đang cố gắng cân bằng giữa công việc và thời gian cho gia đình. Họ chọn dành nhiều sự quan tâm cho người thân và các sở thích cá nhân thay vì chỉ tập trung hoàn toàn vào công việc như trước. Các xu hướng làm việc khác chỉ là thông tin phụ, không cần quan tâm nhiều.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt A thể hiện rõ phong cách thực dụng, tập trung vào hiệu suất và mục tiêu sự nghiệp phù hợp với nhân vật quản lý. Bản tóm tắt B phản ánh đúng ngữ điệu nhẹ nhàng, hướng đến giá trị tinh thần và sự bình yên của người lớn tuổi. Sự khác biệt này hoàn toàn khớp với expected_effect đã đề ra.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ16: Nền tảng văn hóa có làm thay đổi mức độ cộng hưởng của người dùng với cùng một văn bản không?
**Trường kiểm tra:** cultural_background (GENERAL)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Bà Nga nhấn vào phong tục truyền thống (thắp hương, gói bánh chưng, đi chùa); tóm tắt cho Hiếu có thể giữ cả phần xu hướng hiện đại (du lịch nước ngoài, tiệc Tết hiện đại).

### Person A — Bà Nga - gắn bó văn hóa truyền thống Đà Nẵng (bài chòi, lễ hội)
```
Tết Nguyên Đán gần kề, không khí tại TP. Hồ Chí Minh đang rất nhộn nhịp với nhiều hoạt động mua sắm.

Ở các gia đình giữ nếp sống truyền thống, việc chuẩn bị đón Tết vẫn rất chu đáo và đầy đủ. Mọi người dọn dẹp bàn thờ, chuẩn bị mâm ngũ quả, rồi gói bánh chưng, bánh tét cùng con cháu. Chiều 30 Tết, gia đình thắp hương mời tổ tiên về nhà. Sáng mùng Một, cả nhà đi lễ chùa cầu an, sau đó về thực hiện tục chúc Tết, mừng tuổi ông bà và lì xì cho trẻ nhỏ để giữ gìn nét văn hóa quý báu của cội nguồn.

Ngoài ra, một bộ phận người dân tại các thành phố lớn chọn cách đón Tết hiện đại hơn như đi du lịch nước ngoài hoặc đặt tiệc nhà hàng thay vì tự chuẩn bị tại gia.

Về tình hình chung, sức mua tại các chợ khá ổn định. Hiện nay, người dân bắt đầu di chuyển về quê đón Tết khiến giao thông tại các bến xe, nhà ga đông đúc hơn thường ngày.
```

### Person B — Dương Xuân Hiếu - sống chung cư hiện đại, pha trộn văn hóa
```
Tại TP. Hồ Chí Minh, không khí mua sắm Tết đang tăng nhiệt tại các trung tâm thương mại và tuyến đường lớn, đồng thời sức mua của người dân ghi nhận mức ổn định. Giao thông tại các nhà ga, sân bay và bến xe cũng bắt đầu vào giai đoạn cao điểm phục vụ nhu cầu di chuyển.

Khác với các gia đình duy trì nghi lễ truyền thống, lối sống hiện đại tại các đô thị đang trở nên phổ biến hơn. Nhiều cá nhân chọn cách đón Tết linh hoạt như đặt tour du lịch nước ngoài (Nhật Bản, Hàn Quốc, Thái Lan) thay vì đón giao thừa tại nhà. Thay vì tự tay chuẩn bị cỗ bàn, nhóm người này ưu tiên tổ chức tiệc buffet tại nhà hàng, mời đồng nghiệp, trang trí không gian tối giản hoặc đặt sẵn món ăn thông qua các ứng dụng giao hàng. Các địa phương khác cũng có những hoạt động đón xuân riêng biệt.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 1.0
- **Lý do:** Bản tóm tắt A tập trung sâu vào các nghi thức truyền thống như thắp hương, gói bánh và đi lễ chùa, phù hợp với đối tượng Bà Nga. Bản tóm tắt B phản ánh đúng kỳ vọng khi nhấn mạnh vào lối sống hiện đại, du lịch nước ngoài và các tiện ích số, tạo ra sự khác biệt rõ rệt theo đúng mong muốn cá nhân hóa đã đặt ra.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ17: Khi trường HARD (zone, occupation) và trường SOFT (travel_persona) xung đột nhau, tóm tắt có ưu tiên theo HARD không?
**Trường kiểm tra:** zone + occupation (HARD) vs travel_persona (SOFT) - quan hệ uu_tien_hon
**Loại test:** single_constraint
**Kỳ vọng (expected_effect):** Tóm tắt giữ lại phần khám phá tự túc bằng xe máy, ẩm thực vỉa hè, chi phí hợp lý (phù hợp HARD: nông thôn, buôn bán) hơn là phần resort 5 sao/tour cao cấp (dù travel_persona SOFT có xu hướng quốc tế/cao cấp).

### Person A — Chị Mai - Nông Thôn/Buôn bán (HARD) nhưng travel_persona thích quốc tế (SOFT)
```
Mùa nước nổi ở miền Tây Nam Bộ là dịp tuyệt vời để chị trải nghiệm nhịp sống dân dã tại chợ nổi Cái Răng và thưởng thức món ngon vỉa hè ven sông đầy ắp tình người. Nếu muốn chủ động hành trình, chị có thể tự mình chạy xe máy khám phá, cảm nhận từng nhịp đập chân chất của vùng đất này. Ngoài ra, cũng có các dịch vụ du lịch trọn gói sang trọng khác tại đây.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 0.9
- **Lý do:** Bản tóm tắt đã tập trung khai thác các yếu tố trải nghiệm tự túc, xe máy và ẩm thực vỉa hè, phù hợp với profile HARD (nông thôn, buôn bán). Phần du lịch sang trọng chỉ được nhắc đến rất ngắn gọn ở cuối như một lựa chọn phụ, không lấn át nội dung chính, thể hiện sự ưu tiên đúng theo kỳ vọng.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ18: Sự kết hợp giữa nghề nghiệp và khu vực sống có tạo ra yêu cầu tóm tắt đặc thù không?
**Trường kiểm tra:** occupation x zone (HARD x SOFT combo)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Cùng nghề buôn bán nhưng tóm tắt cho Minh (nông thôn) giữ phần giá nông sản/kênh phân phối truyền thống; tóm tắt cho Thảo (đô thị) giữ phần thương mại điện tử/logistics.

### Person A — Minh - Buôn bán, Nông Thôn
```
Tuần qua, giá lúa gạo tại đồng bằng sông Cửu Long biến động mạnh do nhu cầu xuất khẩu tăng. Anh nên theo dõi sát giá thu mua tại các kênh phân phối truyền thống để nắm bắt tình hình buôn bán. Việc kinh doanh hàng tiêu dùng tại các thành phố lớn có xu hướng giảm nhẹ giá. Người tiêu dùng trẻ hiện nay ưu tiên mua hàng online, tạo thách thức cho các chợ và tiệm tạp hóa truyền thống.
```

### Person B — Phạm Thị Thảo - Buôn bán, Đô Thị
```
Giá hàng tiêu dùng tại các siêu thị đô thị có xu hướng giảm nhẹ nhờ tỷ giá ổn định. Đối với các cửa hàng tại thành phố lớn, cần đẩy mạnh thương mại điện tử và logistics để cạnh tranh hiệu quả. Xu hướng người tiêu dùng trẻ ưu tiên đặt hàng online đang tạo ra thách thức đáng kể cho mô hình bán lẻ truyền thống. Giá lúa gạo tại đồng bằng sông Cửu Long biến động do nhu cầu xuất khẩu tăng.
```

### Đánh giá LLM judge
- **Verdict:** FAIL
- **Confidence:** 0.9
- **Lý do:** Cả hai bản tóm tắt đều chứa các thông tin gần như tương tự nhau thay vì phân hóa rõ rệt theo nhu cầu. Bản A (nông thôn) vẫn đề cập nặng về thương mại điện tử, trong khi bản B (đô thị) lại đưa thông tin lúa gạo lên đầu, không phản ánh đúng sự ưu tiên thông tin theo khu vực sống như kỳ vọng.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ19: Mức độ tham gia nghệ thuật (arts_persona) có ảnh hưởng đến khả năng tiếp nhận văn phong giàu hình ảnh/ẩn dụ trong bản tóm tắt không?
**Trường kiểm tra:** arts_persona (SOFT)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Oanh có thể dùng ngôn ngữ giàu hình ảnh/ẩn dụ hơn khi mô tả triển lãm; tóm tắt cho Dung trực tiếp, tường minh hơn.

### Person A — Oanh - đam mê hội họa, thường xuyên dự triển lãm (arts cao)
```
Triển lãm mỹ thuật tại Hải Phòng là điểm hẹn giá trị, nơi những nét cọ sơn dầu lớp và sắc màu tương phản đầy kịch tính khắc họa sâu sắc ảnh hưởng của trường phái biểu hiện trừu tượng. Từng tác phẩm như những nhịp đập nghệ thuật đương đại, mời gọi tư duy học thuật của ta cùng chiêm nghiệm. Các hoạt động cộng đồng khác tại sự kiện chỉ diễn ra thoáng qua.
```

### Person B — Lê Văn Dung - công nhân, ít liên quan nghệ thuật (arts thấp)
```
Triển lãm mỹ thuật đương đại tại thành phố đang mở cửa, trưng bày nhiều tác phẩm sơn dầu giàu cảm xúc với kỹ thuật phối màu ấn tượng. Đây là dịp để bạn đắm mình vào thế giới nghệ thuật, chiêm ngưỡng những nét cọ biểu hiện đầy mê hoặc. Các hoạt động trải nghiệm văn hóa khác tại địa phương cũng đang diễn ra sôi nổi, hứa hẹn mang lại nhiều cảm hứng cho bạn.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 0.95
- **Lý do:** Bản tóm tắt A sử dụng ngôn ngữ giàu tính gợi hình và ẩn dụ như 'nét cọ sơn dầu lớp', 'nhịp đập nghệ thuật', phù hợp với người có chuyên môn nghệ thuật cao. Bản tóm tắt B sử dụng ngôn từ trực tiếp, phổ thông và dễ tiếp cận hơn, phản ánh đúng kỳ vọng về sự cá nhân hóa văn phong cho hai đối tượng người dùng khác nhau.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________


---
## CQ20: Đam mê và sở thích cá nhân có làm tăng ngưỡng chấp nhận độ dài tóm tắt của người dùng trong chủ đề họ yêu thích không?
**Trường kiểm tra:** hobbies_and_interests (SOFT)
**Loại test:** pair_comparison
**Kỳ vọng (expected_effect):** Tóm tắt cho Anh Thanh có thể dài hơn, giữ lại nhiều chi tiết về công thức truyền thống cầu kỳ; tóm tắt cho Phương Hạnh ngắn gọn hơn, chỉ giữ phần công thức nhanh gọn cơ bản.

### Person A — Anh Thanh - đam mê ẩm thực truyền thống lâu dài, muốn truyền nghề
```
Các lớp học nấu món truyền thống tại Hà Nội đang phát triển, giúp người dân gìn giữ công thức gia truyền. Việc học nấu ăn tại nhà hiện có nhiều hình thức khác nhau từ trực tiếp đến trực tuyến. Tôi sẽ tập trung vào các quy trình làm món truyền thống để truyền đạt lại cho thế hệ trẻ trong làng.
```

### Person B — Phương Hạnh - sở thích đa dạng, không gắn bó sâu với ẩm thực
```
Phong trào nấu ăn tại nhà đang nở rộ, từ các lớp học công thức gia truyền vùng miền đến khóa học trực tuyến cho người mới. Đối với bạn, đây là cơ hội tuyệt vời để tự tay chuẩn bị những món ngon đậm đà như bánh đa cua, nem cua bể Hải Phòng, gắn kết gia đình qua căn bếp ấm.
```

### Đánh giá LLM judge
- **Verdict:** PASS
- **Confidence:** 0.9
- **Lý do:** Bản tóm tắt A của Anh Thanh tập trung vào quy trình và mục tiêu truyền nghề phù hợp với tính chất chuyên sâu, trong khi bản B của Phương Hạnh mang tính gợi ý, ngắn gọn và tập trung vào trải nghiệm nhanh. Sự khác biệt về nội dung phản ánh đúng mức độ ưu tiên về chiều sâu cho Anh Thanh và sự khái quát, tiện lợi cho Phương Hạnh như kỳ vọng.

### Đánh giá thủ công (điền vào đây)
- [ ] Đồng ý với judge
- [ ] Không đồng ý, lý do: ______________________
