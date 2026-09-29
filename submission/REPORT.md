# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Phan Duy Bảo
- **MSSV:** 2A202602767
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/pbaodev/K4-L3-DAY13-PhanDuyBao-2A202602767-Monitoring-LLMOps
- **Commit SHA cuối:** _(điền sau khi commit/push lần cuối; lấy bằng `git log -1 --format=%H`)_
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602767` (Langfuse Cloud US region)

## 2. Evidence index

Evidence dạng text đã có sẵn trong repo; ảnh chụp từ Langfuse/dashboard được bổ sung riêng (cột "Trạng thái"). Tất cả dùng đường dẫn tương đối.

| # | Evidence | Đường dẫn | Trạng thái |
|---|---|---|---|
| 01 | Pytest cuối (33 passed) | [evidence/01-pytest.txt](evidence/01-pytest.txt) | có |
| 02 | Log validator (100/100) | [evidence/02-log-validator.txt](evidence/02-log-validator.txt) | có |
| 03 | Dashboard validator (6/6) | [evidence/03-dashboard-validator.txt](evidence/03-dashboard-validator.txt) | có |
| 04 | Structured log | [evidence/04-structured-log.txt](evidence/04-structured-log.txt) | có |
| 05 | PII redaction | [evidence/05-pii-redaction.txt](evidence/05-pii-redaction.txt) | có |
| 06 | Trace list (≥10 trace) | `evidence/06-trace-list.png`; danh sách ID: [evidence/trace-ids.txt](evidence/trace-ids.txt) | ảnh bổ sung sau |
| 07 | Trace waterfall | `evidence/07-trace-waterfall.png` | ảnh bổ sung sau |
| 08 | Trace metadata | `evidence/08-trace-metadata.png` | ảnh bổ sung sau |
| 09 | Prompt versions v1/v2 | `evidence/09-prompt-versions.png` | ảnh bổ sung sau |
| 10 | Prompt rollback | `evidence/10-prompt-rollback.png` | ảnh bổ sung sau |
| 11 | Dashboard runtime | `evidence/11-dashboard-overview.png` | ảnh bổ sung sau |
| 12 | Incident metric | [evidence/12-incident-metric.txt](evidence/12-incident-metric.txt) + `evidence/12-incident-metric.png` | text có, ảnh bổ sung sau |
| 13 | Incident log | [evidence/13-incident-log.txt](evidence/13-incident-log.txt) + `evidence/13-incident-log.png` | text có, ảnh bổ sung sau |
| 14 | Incident trace | [evidence/14-incident-trace.txt](evidence/14-incident-trace.txt) + `evidence/14-incident-trace.png` | text có, ảnh bổ sung sau |
| — | Baseline CP0 | [evidence/baseline/](evidence/baseline/) | có |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (21 records; 20 thiếu required fields/enrichment; 0 correlation ID; PII scrub PASS) | 100/100 (53 records, 27 correlation ID, 0 PII leak) | Baseline: `evidence/baseline/validate_logs.txt`; cuối: `evidence/02-log-validator.txt` (đo trên log mới sau khi xóa log cũ) |
| `validate_dashboard.py` | HỢP LỆ 6/6 panel | HỢP LỆ 6/6 panel | Contract có sẵn trong starter nên baseline đã đạt; validator chỉ kiểm tra cấu trúc, dashboard runtime là `scripts/build_dashboard.py`. `evidence/baseline/validate_dashboard.txt`, `evidence/03-dashboard-validator.txt` |
| `pytest` | 22 passed | 33 passed (thêm test CP1 cho middleware/PII/log, CP2 cho span con và dashboard) | `evidence/baseline/pytest.txt` |
| Số traces hợp lệ | 0 (chưa cấu hình Langfuse, `tracing_enabled=false`) | 40 (mỗi trace 3 observation: root, retrieve, llm-generate) | `evidence/trace-ids.txt` |
| Số PII leak | 0 (validator) | 0 | Input test chứa email/SĐT/CCCD/thẻ: `evidence/05-pii-redaction.txt` |
| Latency P95 / TTFT P95 | 160 ms / 55 ms (10 request) | Bình thường: 207 ms / 55 ms (20 request). Khi incident: 2664 ms / 55 ms (5 request) | Latency trong log đo bên trong agent, chưa gồm thời gian chờ hàng đợi (xem mục 7) |
| Retrieval success rate | 100% (10/10) | 100% (25/25 request `response_sent`) | Incident challenge làm retrieval chậm chứ không làm nó lỗi nên tỷ lệ thành công không đổi |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` gọi `clear_contextvars()` đầu mỗi request, nhận `x-request-id` nếu khớp `^[A-Za-z0-9._-]{1,64}$` (chặn log injection), nếu không thì sinh `req-<8 hex>`; bind vào structlog contextvars, gán `request.state`, trả lại qua header `x-request-id` và `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `chat()` bind `user_id_hash` (sha256 cắt 12 ký tự, không log user_id thô), `session_id`, `feature`, `model`, `env` trước `request_received`, nên mọi log sau trong request đều có. Kèm `ts`, `level`, `service`, `event`, `correlation_id`, latency/ttft/token/cost/quality ở `response_sent`.
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` đứng trước `JsonlFileProcessor` trong chuỗi processor, scrub đệ quy `event`, `payload`, `exception`, `stack`. `app/pii.py` có email, SĐT VN, CCCD, thẻ và thêm passport VN.
- **Cách kiểm chứng kết quả:** `tests/test_correlation_logging.py` + `tests/test_pii.py` (header, ID không an toàn, cô lập giữa request, enrichment, không còn PII thô trong file log); `validate_logs.py` 100/100; request thủ công chứa PII giả (`evidence/05-pii-redaction.txt`).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Key thuộc project `day13-k4-l3a-2A202602767` (Langfuse **US region**, `LANGFUSE_BASE_URL=https://us.cloud.langfuse.com`); 15 trace do tôi tự chạy `load_test.py` và request thủ công, danh sách ở `evidence/trace-ids.txt`.
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (AGENT) → con `retrieve` (RETRIEVER, output chỉ có `doc_count`) và `llm-generate` (GENERATION, có model, `usage_details` input/output, `cost_details` input/output/total, prompt link, `ttft_ms` trong metadata). Input/output của generation đã `scrub_text`. Kiểm tra bằng Langfuse API v2: trace có PII giả (`req-lab-pii01`) không còn email/SĐT/CCCD/thẻ nguyên văn, chỉ có `[REDACTED_*]`.
- **Cách nối trace với log:** `correlation_id` nằm trong metadata của mọi observation (`propagate_attributes`), giống `correlation_id` trong `data/logs.jsonl` và header `x-request-id`; tìm trace bằng cách lọc metadata `correlation_id`.
- **Prompt name:** `day13-chat` (text prompt, giữ 3 biến `feature`, `docs`, `message`). Tạo bằng `scripts/setup_prompts.py create`.
- **Version/label baseline:** v1 — labels `baseline`, `production`.
- **Version/label candidate:** v2 — label `candidate` (thêm yêu cầu trả lời tối đa 3 câu và trích nguồn).
- **Trace ID của mỗi version:** cùng input "What is your refund policy?": `baseline`→v1 `49e2f46c906323be47f0d4562f7fe19e` (req-lab-base-v1); `candidate`→v2 `5e1a994281c07eec6bb270fcfc502349` (req-lab-cand-v2); `production`=v2 sau promote `d38c61327800f0f34516e9e5ae2014cd` (req-lab-prod-v2); `production`=v1 sau rollback `cc2fbe960bfd99d8009f2cf836c2e15e` (req-lab-prod-v1).
- **Cách promote và rollback `production`:** `python scripts/setup_prompts.py promote 2` chuyển label `production` từ v1 sang v2, `rollback 1` chuyển lại v1 (label chỉ nằm trên một version). Mỗi bước restart API để bỏ cache prompt 60s rồi gửi request; metadata trace ghi đúng `prompt_label`/`prompt_version` lấy từ Langfuse (`prompt_source=langfuse`), không hard-code.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `python scripts/build_dashboard.py` (`--watch` để refresh 30s) đọc `data/logs.jsonl` + `config/dashboard.yaml` và sinh `data/dashboard.html` (SVG thuần, không thêm dependency). Sáu panel: latency P50/P95/P99 + TTFT P95, traffic, error rate + breakdown + retrieval success, cost, tokens in/out, quality. Mỗi panel có đơn vị, time range 60 phút, đường threshold và huy hiệu OK/BREACH. Test ở `tests/test_build_dashboard.py`.
- **SLO và lý do chọn:** `fast_successful_requests`: 99.5% request có `response_sent` với latency ≤ 3000ms trong 28 ngày. Baseline đo được P95 ~0.84s, P99 ~1.2s nên 3000ms còn dư khoảng 2.5 lần; incident `rag_slow` đo được P95 = 3856ms nên vượt SLO rõ ràng (chi tiết `config/slo.yaml`).
- **Cách tính error budget:** budget = (1 − 99.5%) = 0.5% tổng request. Ví dụ 10.000 request/28 ngày cho phép tối đa 50 request chậm hoặc lỗi; tương đương ~201.6 phút hỏng hoàn toàn. `request_failed` không có `response_sent` nên cũng đốt budget. Burn rate ≥ 14.4 (1h) thì page, ≥ 3 (6h) thì mở ticket.
- **Ba alert và runbook tương ứng:** `high_latency_p95` (P2, P95 > 2000ms/5m), `high_error_rate` (P1, > 2%/5m), `cost_per_request_spike` (P3, > 0.006 USD/request/10m), đều gửi Slack `#day13-k4-l3a-alerts`, runbook ở `docs/alerts.md`. Ngưỡng kiểm tra bằng incident practice, cùng workload 10 request: `rag_slow` P95 = 3856ms (baseline ~840ms); `tool_fail` error rate 100% (baseline 0%); `cost_spike` chi phí trung bình 0.0079 USD/request (baseline ~0.002).

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, `config/challenge.json` giữ local, không commit)
- **Khoảng thời gian điều tra:** 2026-09-29 09:16:54Z → 09:17:07Z (UTC). Trước đó chạy 10 request bình thường làm mốc; tắt incident sau khi điều tra và chạy lại 10 request để xác nhận hồi phục.
- **Triệu chứng từ metrics:** chỉ latency tăng: P95 664ms → 2665ms (vượt ngưỡng challenge 2000ms và alert `high_latency_p95`), P50 158ms → 2664ms. TTFT P95 ~55ms, cost/request (0.0020 → 0.0021 USD), quality (0.88 → 0.84) và error rate (0%) gần như không đổi. Cả 5 request thuộc `feature=monitoring`. Bảng ở `evidence/12-incident-metric.txt`.
- **Log line và correlation ID liên quan:** `req-37be4072` (`response_sent`, `latency_ms=2664`, `ttft_ms=53`, `tool_success=true`); tương tự `req-ab8d1b9e`, `req-97655b82`. TTFT thấp trong khi tổng latency cao cho thấy LLM không phải bước chậm. Xem `evidence/13-incident-log.txt`.
- **Trace ID và span gây ảnh hưởng:** trace `1729a0af5e9638d86828b655143612c2` (cùng `correlation_id=req-37be4072`): `lab-agent-run` 2.665s = `retrieve` **2.506s** + `llm-generate` 0.159s. Trace khỏe `eb6393b875eae33bb7b5969b43dad3a2`: `retrieve` 0.003s. Span `retrieve` chậm gấp ~830 lần, `llm-generate` không đổi (`evidence/14-incident-trace.txt`).
- **Root cause:** bước retrieval (RAG/vector store) bị chậm thêm ~2.5s cho mọi request; đây là mô phỏng incident `rag_slow` (tôi thấy tên này trong output của `inject_incident.py` nhưng kết luận dựa trên metric → log → trace ở trên: chỉ span `retrieve` tăng, LLM/cost/quality/lỗi không đổi).
- **Fix action:** giảm ảnh hưởng ngay bằng cách tắt nguồn chậm (`python scripts/inject_incident.py --disable`); đo lại sau fix: P95 161ms, error rate 0% (10/10 request). Trong thực tế: đặt timeout retrieval ~500ms và trả câu trả lời fallback khi hết giờ.
- **Preventive measure:** (1) alert `high_latency_p95` (P95 > 2000ms/5m) và thêm span-level alert cho `retrieve`; (2) timeout + circuit breaker + cache cho retrieval; (3) phát hiện khi đo: `chat()` là `async def` nhưng gọi đồng bộ `agent.run`, làm nghẽn event loop nên 5 request đồng thời bị xử lý nối tiếp (client chờ ~13.3s dù `latency_ms` trong log chỉ 2.66s). Nên chuyển sang `def`/`asyncio.to_thread` và đo latency ở middleware để dashboard phản ánh thời gian chờ thật.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Tôi không dùng Streamlit/Grafana cho dashboard mà viết `scripts/build_dashboard.py` bằng thư viện chuẩn + PyYAML, sinh HTML với SVG inline từ `data/logs.jsonl` và `config/dashboard.yaml`. Lý do: `requirements.txt` đã pin phiên bản, thêm dependency nặng dễ làm hỏng cài đặt lại của người chấm; contract YAML là nguồn duy nhất cho tiêu đề, đơn vị và threshold nên dashboard không thể lệch contract; và có test tự động (`tests/test_build_dashboard.py`). Đổi lại, đây là dashboard tĩnh làm mới bằng `--watch`, không phải dashboard live trong Langfuse.
- **Một lỗi/blocker đã gặp:** Sau khi điền key Langfuse, `/health` báo `tracing_enabled: true` nhưng không có trace nào lên và API trả 401 "Invalid credentials".
- **Cách tìm nguyên nhân và xử lý:** `tracing_enabled()` chỉ kiểm tra key có tồn tại chứ không kiểm tra key hợp lệ nên báo `true` sai. Tôi gọi thẳng API Langfuse bằng key và thử từng vùng: cặp key mới hợp lệ ở US (`us.cloud.langfuse.com`) trong khi `.env` cũ trỏ EU, nên nguyên nhân là lệch region chứ không phải key hỏng. Tôi từng kết luận sai là "cả ba vùng đều từ chối" vì script thử nghiệm dùng client Langfuse singleton theo public key, nên cả ba lần gọi dùng chung một host; sau đó tôi kiểm tra lại bằng HTTP trực tiếp. Sửa `LANGFUSE_BASE_URL` sang US rồi xác nhận bằng Langfuse API v2 (cấu trúc trace, token, cost, prompt version). Hai blocker nhỏ khác: (1) tắt API quá sớm sau request khiến một trace chưa kịp gửi, xử lý bằng cách chờ vài giây rồi chạy lại; (2) `validate_logs.py` đọc cả log cũ nên phải lưu baseline rồi đổi tên `data/logs.jsonl` trước khi đo lại.
- **Cách hiểu luồng Metrics → Logs → Traces:** Metrics trả lời "có vấn đề gì và từ khi nào": trong challenge, chỉ P95 latency tăng (664 → 2665 ms) còn TTFT, cost, quality, error rate không đổi. Logs trả lời "request nào": lọc `response_sent` chậm để lấy `correlation_id` (`req-37be4072`), và TTFT thấp cho biết LLM không phải nguyên nhân. Traces trả lời "bước nào": mở trace cùng `correlation_id` thấy `retrieve` 2.506s so với 0.003s của trace bình thường, còn `llm-generate` không đổi. `correlation_id` là chiếc cầu nối log với trace (nằm trong metadata của mọi span), còn trace ID chỉ có ở Langfuse. Kết luận chỉ hợp lệ khi cả ba lớp cùng chỉ về một nguyên nhân.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt là một phần của hành vi hệ thống nhưng thay đổi không qua deploy code, nên cần version và label để biết mỗi request dùng prompt nào. Tôi chạy cùng một input với v1 và v2 và trace ghi đúng version lấy từ Langfuse (không hard-code); `rollback 1` đưa `production` về v1 chỉ bằng đổi label, không cần deploy lại. Token và cost được ghi trên span generation để phát hiện prompt dài hơn hoặc đầu ra tăng: trong practice `cost_spike` chi phí trung bình lên 0.0079 USD/request so với ~0.002. SLO 99.5% request ≤ 3000ms biến "chậm" thành một con số quyết định được, error budget (0.5%, ~201.6 phút/28 ngày) cho biết còn bao nhiêu rủi ro để chấp nhận thay đổi.
- **Điều quan trọng nhất đã học:** Một chỉ số tổng hợp chỉ nói có vấn đề; để biết nguyên nhân phải có log có ID liên kết và trace có span con. Thiếu span con thì waterfall vô dụng, thiếu `correlation_id` thì không nối được hai nguồn. Ngoài ra, "tracing bật" (có key) khác "trace tới được Langfuse", nên phải kiểm chứng dữ liệu thật thay vì tin cờ trạng thái.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - Ảnh chụp Langfuse và dashboard (`06`–`11` và ảnh của `12`–`14`) chưa được đưa vào; hiện chỉ có evidence dạng text cho `12`–`14` và trace ID/log để đối chiếu.
  - Ba alert chỉ là cấu hình khai báo (`config/alert_rules.yaml`, runbook `docs/alerts.md`), chưa nối vào hệ thống alert hay Slack thật; ngưỡng đã kiểm tra bằng incident practice nhưng chưa có cơ chế gửi thông báo.
  - Dashboard là HTML tĩnh sinh từ log, không phải dashboard trong Langfuse.
  - `latency_ms` trong log đo bên trong agent, chưa gồm thời gian chờ do `chat()` là `async` nhưng gọi đồng bộ `agent.run` (5 request đồng thời: log 2.66s, client chờ ~13.3s). Tôi ghi nhận là preventive measure chứ chưa sửa code.
  - Mẫu đo nhỏ (5–25 request mỗi lần), dùng fake LLM và cost ước tính nên P95/P99 chỉ mang tính minh họa.
  - Trong lúc chạy challenge, tên incident lộ ra qua output của `inject_incident.py`; tôi đã nêu ở mục 7 và kết luận vẫn dựa trên bằng chứng ba lớp.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
