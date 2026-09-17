import math
import re
from collections import Counter
from app.modules import repository as repo

def terms(text):
    return re.findall(r"[^\W_]+", text.casefold())

def search(owner, workspace, question, top_k=4):
    candidates = []
    for doc in repo.listing("document", owner, workspace):
        if doc["status"] != "READY":
            continue
        for chunk in doc.get("chunks", []):
            candidates.append({**chunk, "source": doc["name"], "document_id": doc["id"]})
    if not candidates:
        return []
    counters = [Counter(terms(c["text"])) for c in candidates]
    average = max(1, sum(sum(c.values()) for c in counters) / len(counters))
    scores = []
    for chunk, counter in zip(candidates, counters):
        score = 0.0
        for word in set(terms(question)):
            frequency = sum(word in c for c in counters)
            idf = math.log(1 + (len(counters) - frequency + .5) / (frequency + .5))
            tf = counter[word]
            score += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * sum(counter.values()) / average))
        if score > 0:
            scores.append({**chunk, "score": round(score, 4)})
    return sorted(scores, key=lambda c: c["score"], reverse=True)[:top_k]
