#!/usr/bin/env python3
"""
Regenerate both README tables from tools.yaml.

    python render_table.py                 # print both tables
    python render_table.py --write         # rewrite the blocks between the markers
    python render_table.py --check         # exit 1 if README and YAML disagree
    python render_table.py --answers 5000  # entry plans that collect at least 5,000 answers a month

A tracker is a sampling instrument, so the two numbers worth comparing are
how many answers a plan collects and how noisy one prompt's score is at that
sample size. Both are computed here from the plan facts, never typed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from llmvis.stats import half_width

ROOT = Path(__file__).resolve().parent
README = ROOT / "README.md"
RUNS_PER_MONTH = {"daily": 30, "weekly": 4}
REFERENCE_RATE = 0.30  # noise column assumes a prompt sitting at 30% visibility


def load(path: Path = ROOT / "tools.yaml") -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def samples_per_cell(t: dict) -> int | None:
    """Answers one prompt gets on one engine in a month."""
    runs = RUNS_PER_MONTH.get(t["refresh"])
    return runs * t.get("samples_per_run", 1) if runs else None


def answers_per_month(t: dict) -> int | None:
    basis = t["answers_basis"]
    if basis == "stated":
        return t["answers"]
    if basis == "computed":
        runs = RUNS_PER_MONTH[t["refresh"]]
        return t["prompts"] * t["engines"] * runs
    if basis == "credits":
        return t["credits"] // t["credits_per_answer"]
    return None


def cost_per_1k(t: dict) -> float | None:
    n = answers_per_month(t)
    return t["price"] / n * 1000 if n else None


def money(cur: str, v: float) -> str:
    return f"{cur}{v:,.2f}".replace(".00", "")


def noise_cell(t: dict) -> str:
    n = samples_per_cell(t)
    if not n:
        return "n/a"
    return f"±{100 * half_width(REFERENCE_RATE, n):.0f} pts (n={n})"


def basis_cell(t: dict) -> str:
    b = t["answers_basis"]
    if b == "stated":
        return "vendor cap"
    if b == "computed":
        return f"{t['prompts']} prompts x {t['engines']} engines x {RUNS_PER_MONTH[t['refresh']]} runs"
    if b == "credits":
        return f"{t['credits']:,} credits / {t['credits_per_answer']} per answer"
    unit = f"{t['credits']:,} credits, " if t.get("credits") else ""
    return unit + "unit not convertible"


def _table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def matrix(tools: list[dict]) -> str:
    header = ["Tool", "What you get", "Engines at entry", "Collection", "Refresh",
              "One prompt, one engine, one month", "API and export", "Output"]
    rows = [[f"[{t['name']}]({t['url']})", t["kind"], t["engines_note"],
             t["collection"], t["refresh"].capitalize(), noise_cell(t), t["api"], t["output"]]
            for t in tools]
    return _table(header, rows)


def cost(tools: list[dict]) -> str:
    header = ["Tool", "Entry plan", "Price", "Answers per month", "How it was derived",
              "Cost per 1,000 answers", "Trial"]
    rows = []
    for t in tools:
        n, c = answers_per_month(t), cost_per_1k(t)
        rows.append([t["name"], t["entry_plan"], f"{money(t['currency'], t['price'])}/mo, {t['billing']}",
                     f"{n:,}" if n else "n/a", basis_cell(t),
                     money(t["currency"], c) if c else "n/a", t["trial"]])
    return _table(header, rows)


BLOCKS = {"TABLE": matrix, "COST": cost}


def splice(text: str, name: str, body: str) -> str:
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    a, b = text.index(start) + len(start), text.index(end)
    return text[:a] + "\n" + body + "\n" + text[b:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--answers", type=int, help="minimum answers per month at entry")
    a = ap.parse_args(argv)
    tools = load()

    if a.answers is not None:
        fit = [t for t in tools if (answers_per_month(t) or 0) >= a.answers]
        for t in sorted(fit, key=cost_per_1k):
            print(f"{t['name']:<32} {answers_per_month(t):>7,} answers  "
                  f"{money(t['currency'], cost_per_1k(t))} per 1,000")
        if not fit:
            print("no entry plan with a published answer volume reaches that number")
        return 0

    if not (a.write or a.check):
        for name, fn in BLOCKS.items():
            print(f"{name}\n{fn(tools)}\n")
        return 0

    text = README.read_text(encoding="utf-8")
    new = text
    for name, fn in BLOCKS.items():
        new = splice(new, name, fn(tools))
    if a.check:
        if new != text:
            print("README tables are stale, run: python render_table.py --write", file=sys.stderr)
            return 1
        print("README tables match tools.yaml")
        return 0
    README.write_text(new, encoding="utf-8", newline="\n")
    print("README tables updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
