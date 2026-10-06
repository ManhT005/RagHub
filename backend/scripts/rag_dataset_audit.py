"""Audit labels and independent families; generated paraphrases cannot satisfy release size."""

REQUIRED_FORMATS = {"markdown", "pdf_native", "pdf_table", "pdf_scan", "docx", "xlsx", "html"}
REQUIRED_CATEGORIES = {
    "same_document_multi_chunk",
    "multi_document",
    "conflicting",
    "versioned",
    "hard_negative",
    "ambiguous",
    "numeric_date",
    "no_diacritics",
    "typo",
    "vi_en",
    "prompt_injection",
}


def main():
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()
    report = audit_dataset(json.loads(args.qa.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.gate and not report["release_eligible"]:
        raise SystemExit(2)


def audit_dataset(cases):
    ids, families, issues, formats = set(), {}, [], set()
    reviewed, categories = 0, set()
    for case in cases:
        case_id = case["id"]
        if case_id in ids:
            issues.append(f"duplicate ID: {case_id}")
        ids.add(case_id)
        family = case.get("family_id", case.get("origin_case_id", case_id))
        split = case.get("split")
        if split not in {"calibration", "holdout"}:
            issues.append(f"missing/invalid split: {case_id}")
        if family in families and families[family] != split:
            issues.append(f"family crosses splits: {family}")
        families[family] = split
        if case.get("review_status") != "reviewed":
            continue
        if not case.get("family_id"):
            issues.append(f"reviewed case needs an independent family ID: {case_id}")
        facts = case.get("expected_facts", [])
        if case.get("answerable") and (
            not facts or any(not f.get("supporting_chunk_ids") for f in facts)
        ):
            issues.append(f"missing reviewed fact support: {case_id}")
            continue
        reviewed += 1
        formats.add(case.get("format", ""))
        categories.update(case.get("categories", []))
    reviewed_families = {
        c.get("family_id", c.get("origin_case_id", c["id"]))
        for c in cases
        if c.get("review_status") == "reviewed"
    }
    missing_formats = sorted(REQUIRED_FORMATS - formats)
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    return {
        "cases": len(cases),
        "families": len(families),
        "reviewed_cases": reviewed,
        "reviewed_families": len(reviewed_families),
        "missing_formats": missing_formats,
        "missing_categories": missing_categories,
        "issues": issues,
        "release_eligible": reviewed == len(cases)
        and len(reviewed_families) >= 200
        and not issues
        and not missing_formats
        and not missing_categories
        and {"calibration", "holdout"} <= set(families.values()),
    }


if __name__ == "__main__":
    main()
