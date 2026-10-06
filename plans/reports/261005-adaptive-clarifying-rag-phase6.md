# Phase 6 - Benchmark va release gates cho Adaptive Clarifying RAG

Ngay: 2026-10-05
Branch: `feature/selfhost-rag-pipeline-upgrade`

## Ket qua nhanh

- Da them benchmark offline lap lai duoc cho lop `ClarificationPolicy`.
- Artifact moi: `artifacts/rag_clarification_eval.json`.
- Dataset moi: `backend/tests/fixtures/rag_golden/clarification_cases.json` gom 20 case.
- Runner moi: `backend/scripts/evaluate_clarification_policy.py`.
- Test gate moi: `backend/tests/test_clarification_eval.py`.

## Nhom case da bao phu

- `ambiguous_requires_clarification`: cau hoi mo ho can hoi lai.
- `followup_resolution`: cau follow-up ngan sau clarification phai du dieu kien tra loi.
- `should_answer_directly`: cau hoi ro khong bi hoi lai thua.
- `out_of_scope_no_citation`: injection / ngoai pham vi phai refuse_or_redirect, khong tao citation gia.

## Metrics dat duoc

| Metric | Ket qua | Nguong | Trang thai |
|---|---:|---:|---|
| clarification_precision | 1.00 | >= 0.85 | PASS |
| clarification_recall | 1.00 | >= 0.80 | PASS |
| unnecessary_clarification_rate | 0.00 | <= 0.15 | PASS |
| followup_resolution_rate | 1.00 | >= 0.85 | PASS |
| answerable_direct_pass_rate | 1.00 | >= 0.90 | PASS |
| citation_precision | 1.00 | = 1.00 | PASS |
| rejection_f1 | 1.00 | >= 0.90 | PASS |

## Test da chay

- `backend/.venv/Scripts/python.exe scripts/evaluate_clarification_policy.py --out ../artifacts/rag_clarification_eval.json` - PASS.
- `backend/.venv/Scripts/python.exe -m pytest tests/test_clarification_eval.py tests/test_chatbot_clarification_config.py` - PASS, 5 passed.
- `backend/.venv/Scripts/python.exe -m py_compile scripts/evaluate_clarification_policy.py tests/test_clarification_eval.py` - PASS.

## So sanh voi truoc do

Truoc update, RAG chi co benchmark retrieval/chat production golden, nhung chua co gate rieng cho hanh vi hoi lai. Sau update, phan adaptive clarification co:

- Dataset rieng cho ambiguous/direct/follow-up/refusal.
- Runner deterministic, khong phu thuoc provider, khong ton token.
- Threshold gate fail-fast trong CI/test.
- Artifact JSON de audit lai ket qua theo commit.

## Gioi han con lai

Benchmark nay chi chung minh lop decision policy va follow-up offline. No khong thay the live benchmark end-to-end co ingest, retrieval, provider chat, SSE client va latency. De xac nhan xuat ban cuoi cung van can chay lai `backend/scripts/run_production_eval.py` trong moi truong provider on dinh, tranh rate limit.