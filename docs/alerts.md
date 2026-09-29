# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.
Cấu hình máy đọc được nằm ở [../config/alert_rules.yaml](../config/alert_rules.yaml); SLO ở [../config/slo.yaml](../config/slo.yaml).

Baseline dùng để chọn ngưỡng (fake LLM, Langfuse bật): P95 ~0.84s, error rate 0%, chi phí ~0.002 USD/request.

Điều tra luôn đi theo thứ tự **Metrics → Logs → Traces**: dashboard cho biết triệu chứng và khoảng thời gian, `data/logs.jsonl` cho `correlation_id` của request xấu, rồi mở trace Langfuse có cùng `correlation_id`.

## Alert 1

- Tên: `high_latency_p95`
- Severity: P2
- Duration: 5 phút
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (latency ≤ 3000ms, target 99.5%/28d)
- Điều kiện và thời gian duy trì: P95 `response_sent.latency_ms` > 2000ms liên tục 5 phút. Ngưỡng 2000ms cao hơn ~2.4 lần P95 baseline nhưng thấp hơn giới hạn SLO 3000ms, để cảnh báo trước khi đốt budget nhanh.
- Ảnh hưởng tới người dùng: câu trả lời đến chậm, một phần request sắp vượt 3000ms và tính vào error budget.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel *Latency*: P50 tăng cùng P95 (chậm toàn bộ) hay chỉ P99 (đuôi)? Ghi lại khoảng thời gian.
  2. Lọc `data/logs.jsonl` các `response_sent` có `latency_ms` > 2000 trong khoảng đó, lấy một `correlation_id`; so `ttft_ms` để biết chậm ở đầu hay ở cuối.
  3. Mở trace cùng `correlation_id` trên Langfuse, so thời gian span `retrieve` với `llm-generate`; span nào chiếm phần lớn thời gian là nguyên nhân.
- Mitigation tạm thời: nếu chậm ở `retrieve` (ví dụ `rag_slow`), tắt hoặc bỏ qua retrieval, dùng câu trả lời fallback và đặt timeout cho vector store; nếu chậm ở `llm-generate`, chuyển sang model dự phòng hoặc giảm độ dài đầu ra.
- Owner: phanduybao-oncall

## Alert 2

- Tên: `high_error_rate`
- Severity: P1
- Duration: 5 phút
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` và guardrail `error_rate_pct_max: 2`
- Điều kiện và thời gian duy trì: `request_failed / request_received` > 2% liên tục 5 phút. Baseline là 0%, nên 2% là tín hiệu thật, không phải nhiễu.
- Ảnh hưởng tới người dùng: request trả HTTP 500, người dùng không nhận được câu trả lời; mỗi request lỗi đốt trực tiếp error budget.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel *Errors*: xem breakdown `error_type` và *retrieval success %* (guardrail ≥ 90%).
  2. Lọc log `event == "request_failed"`, lấy `correlation_id` và đọc `error_type`, `tool_name`, `payload.detail`.
  3. Mở trace cùng `correlation_id`: span `retrieve` hay `llm-generate` có level ERROR; đối chiếu `/health` xem incident nào đang bật.
- Mitigation tạm thời: nếu lỗi do retrieval (`RuntimeError: Vector store timeout`), trả lời bằng ngữ cảnh rỗng kèm cảnh báo thay vì lỗi 500, hoặc tắt incident đang bật; rollback thay đổi gần nhất (kể cả label prompt `production`) nếu lỗi bắt đầu ngay sau lần deploy.
- Owner: phanduybao-oncall

## Alert 3

- Tên: `cost_per_request_spike`
- Severity: P3
- Duration: 10 phút
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (chi phí/ngày)
- Điều kiện và thời gian duy trì: chi phí trung bình mỗi request > 0.006 USD liên tục 10 phút (baseline ~0.002 USD, tức khoảng 3 lần). Dùng chi phí trên mỗi request thay vì tổng để không phụ thuộc lưu lượng.
- Ảnh hưởng tới người dùng: người dùng không thấy ngay, nhưng chi phí tăng nhanh có thể chạm trần ngân sách ngày và buộc phải chặn dịch vụ.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel *Cost* và *Tokens*: tăng ở `tokens_out` hay `tokens_in`? Ghi lại thời điểm bắt đầu.
  2. Lọc `response_sent` có `cost_usd` cao, lấy `correlation_id`, so `tokens_in`/`tokens_out` với mức baseline.
  3. Mở trace cùng `correlation_id`, xem `usage_details`/`cost_details` của span `llm-generate` và `prompt_version` trong metadata (prompt mới có làm đầu ra dài hơn không).
- Mitigation tạm thời: đặt giới hạn `max_tokens`, rút gọn prompt, rollback label `production` về version prompt trước; nếu vẫn tăng, giới hạn tần suất theo user.
- Owner: phanduybao-oncall
