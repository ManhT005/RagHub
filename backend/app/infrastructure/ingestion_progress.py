STAGE_ORDER = {
    name: i
    for i, name in enumerate(
        ("UPLOADED", "QUEUED", "PARSING", "CHUNKING", "EMBEDDING", "INDEXING", "READY")
    )
}


def advance_progress(current, proposed):
    return max(current or 0, proposed)


def advance_stage(current, proposed):
    if proposed == "FAILED":
        return proposed
    return proposed if STAGE_ORDER.get(proposed, -1) >= STAGE_ORDER.get(current, -1) else current
