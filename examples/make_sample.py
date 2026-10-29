#!/usr/bin/env python3
"""
Rebuild examples/answers.example.jsonl, a synthetic answer log for demos.

Every brand in it is fictional. The log is seeded so it is identical on
every run. Two things are planted on purpose:

  * Perplexity mention rate jumps in the final week (a real change).
  * ChatGPT wobbles around one flat rate (noise that looks like a trend).

    python examples/make_sample.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

SEED = 7
START = dt.date(2026, 9, 28)  # a Monday, so the log covers four full ISO weeks
DAYS = 28
PROMPTS = [
    "best invoice automation software for small agencies",
    "invoice automation tools that sync with Xero",
    "who can help me automate accounts payable",
    "best AP automation platform for SaaS startups",
    "cheapest invoice OCR tool with an API",
    "invoice approval workflow software for remote teams",
]
RIVALS = ["Quillstack", "Orbitly", "Fenwick Ledger"]
# engine -> (mention rate weeks 1 to 3, mention rate week 4, chance a mention is also cited)
ENGINES = {
    "chatgpt": (0.35, 0.35, 0.30),
    "perplexity": (0.25, 0.55, 0.80),
    "gemini": (0.20, 0.20, 0.15),
    "ai-overviews": (0.30, 0.32, 0.70),
}
SOURCES = [
    "https://www.g2.com/categories/accounts-payable-automation",
    "https://www.reddit.com/r/Accounting/comments/abc123/",
    "https://quillstack.example/blog/ap-automation",
    "https://orbitly.com/compare",
]


def build() -> list[dict]:
    rng = random.Random(SEED)
    rows = []
    for day in range(DAYS):
        date = START + dt.timedelta(days=day)
        late = day >= 21
        for engine, (early_rate, late_rate, cite_rate) in ENGINES.items():
            rate = late_rate if late else early_rate
            for prompt in PROMPTS:
                names = rng.sample(RIVALS, k=rng.randint(1, 3))
                sources = rng.sample(SOURCES, k=rng.randint(0, 3))
                if rng.random() < rate:
                    names.insert(rng.randint(0, len(names)), "Lumora")
                    if rng.random() < cite_rate:
                        sources.append("https://lumora.io/features/approvals")
                text = f"For '{prompt}', teams usually shortlist {', '.join(names)}."
                rows.append({"date": date.isoformat(), "engine": engine, "prompt": prompt,
                             "text": text, "sources": sources})
    return rows


if __name__ == "__main__":
    out = Path(__file__).with_name("answers.example.jsonl")
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for r in build():
            fh.write(json.dumps(r) + "\n")
    print(f"wrote {out}")
