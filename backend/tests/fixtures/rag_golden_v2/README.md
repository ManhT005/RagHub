# Golden V2 review draft

`qa.draft.json` contains 210 generated cases in 30 question families, derived
from the existing `../rag_golden/qa.json` and its nine Markdown documents.
There are **zero reviewed V2 cases**. This file is a review backlog, not a
production release dataset. The original 30-case suite remains unchanged.

Each family has seven variants: original, polite, document scope, short answer,
source request, Vietnamese without diacritics, and Vietnamese/English mixed.
All variants inherit the original split: 140 calibration and 70 holdout cases.
Keep families together when splitting or sampling. These are 30 independent
question families, not 210 independent factual questions.

Reference facts, forbidden claims and logical document/chunk IDs are inherited.
The generated `expected_facts.supporting_chunk_ids` are provisional allocations
of the original case-level references. A reviewer must inspect the actual source
and verify each fact-to-chunk link before changing `review_status` to `reviewed`.
Map logical fixture IDs to actual runtime chunk IDs for production answer reviews.

Coverage still needs distinct source documents and reviewed cases for DOCX
headings, XLSX, PDF tables, scanned PDF/OCR, same-document multi-chunk answers,
conflicting/versioned documents and noisy/typo questions. Paraphrases do not
close these gaps or establish production quality.

Regenerate from the repository root:

```powershell
.venv/Scripts/python.exe backend/scripts/generate_golden_draft.py --out backend/tests/fixtures/rag_golden_v2/qa.draft.json
```

For semantic support review, use `backend/scripts/score_fact_support.py` and the
[operations runbook](../../../../../docs/runbook-rag-operations.md).
