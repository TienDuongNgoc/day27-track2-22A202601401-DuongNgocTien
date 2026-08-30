# AI Agent Decision Log — Lab 27

## Decision 1: Nâng cấp Data Contract Validator với Strict Type Checking & Quarantine Mechanism
- **Hypothesis:** Việc dùng `pd.to_numeric(..., errors='coerce')` sẽ âm thầm nuốt các lỗi type drift (chẳng hạn chuỗi không hợp lệ trong trường số nguyên hoặc số thực), dẫn đến dữ liệu bẩn lọt vào staging mà pipeline vẫn báo SUCCESS.
- **Prompt / request to agent:** Nâng cấp `src/contract_validator.py` hỗ trợ kiểm tra kiểu dữ liệu nghiêm ngặt (integer, number, datetime, boolean, string), kiểm tra độ tươi dữ liệu (freshness), phân cấp severity và cung cấp hàm `quarantine_records()`.
- **Agent proposal:** Tạo các hàm helper kiểm tra type an toàn (`_is_valid_integer`, `_is_valid_number`, `_is_valid_datetime`), thêm check type/range/freshness độc lập, và cài đặt `quarantine_records(df, contract)` tách riêng dòng hợp lệ và dòng vi phạm.
- **Evidence/test:** `pytest tests_public/test_contracts.py` và `test_contract_type_drift_detection` đều PASS 100%.
- **Accept / reject / revise:** **Accept**.
- **Why:** Giúp phát hiện sớm type drift và cô lập dữ liệu lỗi ngay tại cửa ngõ ingestion mà không làm gián đoạn toàn bộ batch.

---

## Decision 2: Bảo vệ Mô hình dbt Mart và Thêm dbt Native Unit Tests
- **Hypothesis:** Khi bảng `customers` có nhiều bản ghi active cho cùng một `customer_id` (do SCD type 2 lỗi hoặc trùng lặp), phép join trong `fct_daily_revenue.sql` sẽ làm nhân bản số dòng đơn hàng và đội doanh thu (revenue inflation) mà SQL không báo lỗi.
- **Prompt / request to agent:** Viết dbt native unit test nhỏ nhất để expose hiện tượng revenue inflation và cập nhật model để chống lỗi fan-out.
- **Agent proposal:** Viết file `dbt_project/models/marts/unit_tests.yml` với 2 unit test cases (`completed_orders_sum_to_expected_revenue` và `prevent_revenue_inflation_on_duplicate_active_customers`), đồng thời sửa model `fct_daily_revenue.sql` dùng `distinct customer_id` khi trích xuất active customers.
- **Evidence/test:** Chạy `dbt build` hoàn thành 19/19 nodes (bao gồm 2 seeds, 3 models, 12 data tests, 2 unit tests) đạt trạng thái PASS 100%.
- **Accept / reject / revise:** **Accept**.
- **Why:** Phân biệt rõ data test (kiểm tra data nguồn) và unit test (kiểm tra logic transformation SQL với mock inputs cô lập).

---

## Decision 3: Thiết kế Context-Aware Statistical Anomaly Detector (MAD + Seasonality)
- **Hypothesis:** Z-score truyền thống rất nhạy cảm với ngoại lai (outliers làm tăng độ lệch chuẩn) và thất bại khi dữ liệu có tính chu kỳ tuần (seasonality) như ngày cuối tuần có volume thấp hơn ngày thường.
- **Prompt / request to agent:** Cải tiến `observability/anomaly.py` với phương pháp MAD (Median Absolute Deviation), xử lý trường hợp `mad == 0`, và làm cho `method="auto"` tự động nhận biết context (`day_of_week`, `same_segment_history`).
- **Agent proposal:** Cài đặt `mad_detector` có fallback sang mean absolute deviation khi `mad == 0`; trong `auto` mode, ưu tiên lọc `same_segment_history` và phối hợp cả MAD lẫn Z-score.
- **Evidence/test:** `test_mad_zero_edge_case` và `test_auto_context_seasonality` PASS; bắt chính xác kịch bản `volume_drop` khi giảm 75% volume.
- **Accept / reject / revise:** **Accept**.
- **Why:** Giảm thiểu triệt để false positives vào cuối tuần mà vẫn bắt được các đợt sụt giảm volume thực sự.

---

## Decision 4: Triển khai Multi-Window Burn Rate Alerting Policy theo Chuẩn Google SRE
- **Hypothesis:** Cảnh báo dựa trên single-window threshold thường gây ra "báo động giả" (alert fatigue) khi có transient spike ngắn hạn dù error budget chưa bị đe dọa nghiêm trọng.
- **Prompt / request to agent:** Cài đặt hàm `evaluate_multiwindow_burn()` trong `observability/slo.py` để phân biệt transient spike và sustained fast burn.
- **Agent proposal:** So sánh đồng thời `short_window_burn` và `long_window_burn`. Chỉ kích hoạt PAGE (Critical) khi cả 2 cửa sổ đều vượt ngưỡng cao; nếu chỉ có short-window cao thì chỉ ghi nhận Warning (transient spike, no page).
- **Evidence/test:** `test_sre_multiwindow_burn_rate` xác nhận transient spike (short=14x, long=1.2x) trả về `page=False, severity="warning"`, trong khi sustained burn trả về `page=True, severity="critical"`.
- **Accept / reject / revise:** **Accept**.
- **Why:** Đạt tiêu chuẩn SRE thực tế, bảo vệ on-call engineer khỏi việc bị page vô ích vào ban đêm.

---

## Decision 5: Traversal Lineage Đa Tầng (Column-Level Transitive Lineage)
- **Hypothesis:** Starter lineage chỉ trả về direct children của node, khiến cho việc đánh giá blast radius bị thiếu các tài nguyên hạ tầng ở tầng 2, tầng 3 (transitive downstream).
- **Prompt / request to agent:** Cải tiến `get_column_downstream()` trong `observability/lineage.py` để duyệt toàn bộ đồ thị theo thuật toán BFS.
- **Agent proposal:** Viết hàm BFS traversal duyệt qua tất cả downstream columns qua nhiều bước nhảy (multi-hop).
- **Evidence/test:** `test_transitive_column_lineage` xác nhận trace từ `raw_orders.order_id` ra cả `stg_orders.order_id`, `fct_daily_revenue.completed_order_rows` và `dashboard.total_orders`.
- **Accept / reject / revise:** **Accept**.
- **Why:** Cho phép xác định chính xác blast radius khi một trường dữ liệu nguồn bị lỗi hoặc thay đổi schema.
