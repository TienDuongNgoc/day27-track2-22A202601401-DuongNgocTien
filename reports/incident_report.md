# Incident Report — Data Reliability Game Day (Lab 27)

## Severity
**P1 — Critical (Data Integrity & Financial Reporting Impact)**

## Summary
CEO Dashboard báo cáo doanh thu biến động bất thường và Support AI Agent cung cấp chính sách hoàn tiền lỗi thời (stale refund policy) cho khách hàng, mặc dù hệ thống pipeline ETL vẫn báo trạng thái `SUCCESS`. Quá trình điều tra đa tầng (Contracts, dbt, Anomaly Detection, Lineage, SLO) đã xác định được chuỗi lỗi gồm:
1. **Duplicate Primary Keys** trên bảng `orders` gây trùng lặp bản ghi và sai lệch aggregation.
2. **Partial Ingestion (Volume Drop)** làm thiếu hụt 75% dữ liệu giao dịch trong batch.
3. **Stale Knowledge Base (Freshness Breach)** dẫn đến RAG model index tài liệu chính sách cũ (-3 giờ so với SLA 60 phút).
4. **Dimension Fan-out Risk** trong transformation model `fct_daily_revenue` khi join với bảng `customers` có nhiều SCD active records.

## Detection
- **Signal 1:** Data Contract Validation báo 1 critical error trên `order_id` (check `unique` thất bại).
- **Signal 2:** Statistical Anomaly Detector (MAD / Auto Context-aware) phát hiện row-count volume drop bất thường (`score=9.66 > threshold=3.0`).
- **Signal 3:** Freshness Contract & RAG SLO ghi nhận độ trễ tài liệu `kb_documents` vượt quá `max_delay_minutes=60`.
- **First observed time:** 2026-08-30 14:00:00 UTC trong chu kỳ chạy batch định kỳ.

## Root Cause
1. **Source Data Ingestion Failures:**
   - Hệ thống webhook upstream retry không idempotent dẫn đến việc duplicate các order records (duplicate order_id).
   - Network timeout ngắt kết nối giữa chừng trong quá trình sync orders gây mất 75% số dòng giao dịch (volume drop).
2. **Knowledge Base Publishing Pipeline Stall:**
   - Pipeline cập nhật tài liệu chính sách từ CMS bị treo, không đồng bộ phiên bản chính sách hoàn tiền mới nhất (published_at trễ 180 phút).
3. **Transformation SQL Vulnerability:**
   - Model `fct_daily_revenue.sql` join trực tiếp với `stg_customers` mà không deduplicate các active customer version, khiến doanh thu bị nhân đôi nếu có SCD active rows trùng lặp.

## Evidence
1. **Evidence 1 (Contract Validation & GX):** `validate_dataframe()` và GX Checkpoint bắt được lỗi `ExpectColumnValuesToBeUnique` trên `order_id` (duplicate_rows > 0).
2. **Evidence 2 (Statistical Baseline):** Anomaly detector phương pháp `auto:context_aware` (MAD kết hợp Z-score) xác định volume 150 rows lệch chuẩn đáng kể so với lịch sử cùng ngày.
3. **Evidence 3 (dbt Unit Tests & Singular Tests):** dbt unit test `prevent_revenue_inflation_on_duplicate_active_customers` và singular test `assert_no_active_customer_duplicates.sql` bắt được nguy cơ nhân bản doanh thu khi customer dimension có duplicate active records.

## Blast Radius
```text
[Incoming Source]
  ├── orders.csv (Duplicate PK / Volume Drop)
  │     └── stg_orders (View)
  │           └── fct_daily_revenue (Mart Table)
  │                 └── CEO Revenue Dashboard (Downstream Consumer)
  │
  ├── customers.csv (SCD Active Duplicates)
  │     └── stg_customers (View)
  │           └── fct_daily_revenue (Mart Table)
  │
  └── kb_documents.jsonl (Stale Timestamp)
        └── Validation & Active KB
              └── RAG Embeddings / Vector Search
                    └── Customer Support AI Agent (Policy Refund Bot)
```

## Mitigation
1. **Block & Quarantine Pipeline:** Kích hoạt cơ chế `quarantine_records()` trong contract validator để chặn các order_id trùng lặp và tách bản ghi lỗi ra bảng cách ly (`data/quarantine/`), không để lọt vào staging/marts.
2. **Protect Mart Transformation:** Cập nhật `fct_daily_revenue.sql` sử dụng `distinct customer_id` khi join `active_customers` để ngăn chặn hoàn toàn hiện tượng fan-out revenue inflation.
3. **Trigger KB Re-sync:** Restart crawler đồng bộ CMS knowledge base và force re-indexing RAG vector store.

## Recovery
- Chạy `make reset` và đồng bộ lại baseline dữ liệu sạch.
- Re-run `make dbt` để build lại toàn bộ mô hình và kiểm tra 19/19 tests pass.
- Chạy `make baseline` xác nhận chỉ số an toàn và SLO phục hồi về 100%.

## Verification
- [x] Contract healthy: Tất cả các checks (unique, not_null, accepted_values, type, range, freshness) đều PASS.
- [x] dbt tests healthy: 12 generic data tests, 2 singular tests và 2 unit tests PASS.
- [x] Anomaly returned to expected range: Row count và KB text length nằm trong ngưỡng thống kê bình thường.
- [x] SLO healthy / budget understood: Error budget burn rate < 1.0, không có vi phạm hay paging alert.
- [x] Downstream output verified: CEO Dashboard và Support AI Agent hiển thị đúng doanh thu và chính sách hoàn tiền hiện hành.

## Prevention / Action Items
| Action | Owner | Deadline | Why |
|---|---|---|---|
| Bổ sung Data Contract Checkpoint vào CI/CD upstream ingestion | Data Platform Team | 2026-09-05 | Chặn duplicate PK và type drift ngay tại entrypoint trước khi lưu vào warehouse |
| Cài đặt Multi-window Burn Rate Alerting (Google SRE standard) | Observability Team | 2026-09-08 | Tránh alert fatigue do transient spike, chỉ page on-call khi sustained fast burn |
| Tích hợp dbt native unit tests vào pre-merge CI checks | Analytics Eng Team | 2026-09-06 | Ngăn ngừa lỗi logic SQL join và SCD dimension inflation |
| Thêm automated KB freshness monitor & embedding drift detector | AI/RAG Eng Team | 2026-09-10 | Đảm bảo Support Agent luôn dùng chính sách mới nhất, phát hiện embedding shift |
