"""
Score an answer log: mention rate, citation rate and share of voice, each
with a Wilson interval, grouped any way you like. Standard library only.

Input is one row per collected answer, from any tracker export, an API such
as cloro, or your own collector. JSON Lines or CSV, with these fields:

    date     2026-10-01
    engine   chatgpt | perplexity | gemini | ai-overviews | ...
    prompt   the question that was asked
    text     the answer text
    sources  cited URLs (a JSON list, or space separated in CSV)

    python -m llmvis.score examples/answers.example.jsonl --brand examples/brand.example.json
    python -m llmvis.score answers.csv --brand brand.json --by engine
    python -m llmvis.score answers.jsonl --brand brand.json --by engine --diff
    python -m llmvis.score answers.jsonl --brand brand.json --by engine --diff --bonferroni
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path
from urllib.parse import urlparse

from .stats import compare, wilson


# ---------- loading ----------

def load_answers(path: str | Path) -> list[dict]:
    path = Path(path)
    rows: list[dict] = []
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                r["sources"] = (r.get("sources") or "").split()
                rows.append(r)
    else:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    for r in rows:
        r.setdefault("sources", [])
        r.setdefault("text", "")
    return rows


def load_brand(path: str | Path) -> dict:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg.setdefault("aliases", [cfg["brand"]])
    cfg.setdefault("domains", [])
    cfg.setdefault("competitors", {})
    return cfg


# ---------- matching ----------

def _pattern(aliases: list[str]) -> re.Pattern:
    # Word boundaries so "Orbit" does not match "Orbitly". Longest alias first.
    alts = sorted((re.escape(a) for a in aliases), key=len, reverse=True)
    return re.compile(r"(?<![\w.])(?:" + "|".join(alts) + r")(?![\w])", re.IGNORECASE)


def host(url: str) -> str:
    h = urlparse(url if "://" in url else "https://" + url).hostname or ""
    return h[4:] if h.startswith("www.") else h


def cites(sources: list[str], domains: list[str]) -> bool:
    hosts = {host(u) for u in sources}
    return any(h == d or h.endswith("." + d) for h in hosts for d in domains)


class Matcher:
    def __init__(self, cfg: dict):
        self.brand = cfg["brand"]
        self.brand_re = _pattern(cfg["aliases"])
        self.domains = cfg["domains"]
        self.rivals = {name: _pattern(al or [name]) for name, al in cfg["competitors"].items()}

    def score(self, row: dict) -> dict:
        text = row.get("text", "")
        mentioned = bool(self.brand_re.search(text))
        rivals = [n for n, rx in self.rivals.items() if rx.search(text)]
        return {
            "mentioned": mentioned,
            "cited": cites(row.get("sources", []), self.domains),
            "rivals": rivals,
        }


# ---------- aggregation ----------

def group_key(row: dict, by: str) -> str:
    if by == "overall":
        return "all"
    if by == "week":
        d = dt.date.fromisoformat(str(row["date"])[:10])
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    return str(row.get(by, ""))


def aggregate(rows: list[dict], m: Matcher, by: str) -> "OrderedDict[str, dict]":
    acc: dict[str, dict] = defaultdict(lambda: {"n": 0, "mentions": 0, "citations": 0, "brand_slots": 0, "all_slots": 0})
    for r in rows:
        s = m.score(r)
        a = acc[group_key(r, by)]
        a["n"] += 1
        a["mentions"] += s["mentioned"]
        a["citations"] += s["cited"]
        # Share of voice: each tracked brand counts once per answer it appears in.
        a["brand_slots"] += s["mentioned"]
        a["all_slots"] += s["mentioned"] + len(s["rivals"])
    return OrderedDict(sorted(acc.items()))


def _fmt(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:5.1f}% [{100 * lo:4.1f}, {100 * hi:4.1f}]"


def render(groups: "OrderedDict[str, dict]", by: str) -> str:
    head = [by, "answers", "mention rate [95% CI]", "citation rate [95% CI]", "share of voice"]
    body = []
    for key, a in groups.items():
        sov = f"{100 * a['brand_slots'] / a['all_slots']:.1f}%" if a["all_slots"] else "n/a"
        body.append([key, str(a["n"]), _fmt(a["mentions"], a["n"]), _fmt(a["citations"], a["n"]), sov])
    widths = [max(len(r[i]) for r in [head] + body) for i in range(len(head))]
    line = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
    return "\n".join([line(head), line(["-" * w for w in widths])] + [line(r) for r in body])


def diff_last_two_weeks(rows: list[dict], m: Matcher, by: str, bonferroni: bool = False) -> str:
    """Last ISO week vs the one before, per group, with a significance call.

    Testing four engines at alpha 0.05 gives roughly a one in five chance that
    at least one flat engine gets flagged. --bonferroni divides alpha by the
    number of groups tested so a CHANGE means something across the whole set.
    """
    weeks = sorted({group_key(r, "week") for r in rows})
    if len(weeks) < 2:
        return "need at least two weeks of data for --diff"
    prev, last = weeks[-2], weeks[-1]
    cells: dict[str, dict[str, list[int]]] = defaultdict(lambda: {prev: [0, 0], last: [0, 0]})
    for r in rows:
        w = group_key(r, "week")
        if w in (prev, last):
            c = cells[group_key(r, by)][w]
            c[0] += m.score(r)["mentioned"]
            c[1] += 1
    alpha = 0.05 / len(cells) if bonferroni else 0.05
    out = [f"mention rate, {prev} -> {last}, alpha {alpha:.4f}"]
    for key in sorted(cells):
        (k1, n1), (k2, n2) = cells[key][prev], cells[key][last]
        delta, pv = compare(k1, n1, k2, n2)
        call = "CHANGE" if pv < alpha else "noise"
        out.append(f"  {key:<14} {k1:>3}/{n1:<3} -> {k2:>3}/{n2:<3} {100 * delta:+6.1f} pts  p={pv:.3f}  {call}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m llmvis.score")
    ap.add_argument("answers", help="answers .jsonl or .csv")
    ap.add_argument("--brand", required=True, help="brand config JSON")
    ap.add_argument("--by", default="overall", choices=["overall", "engine", "prompt", "week"])
    ap.add_argument("--diff", action="store_true", help="compare the last two weeks per group")
    ap.add_argument("--bonferroni", action="store_true", help="correct --diff for testing many groups")
    a = ap.parse_args(argv)

    rows = load_answers(a.answers)
    m = Matcher(load_brand(a.brand))
    if not rows:
        print("no answers in file", file=sys.stderr)
        return 1
    print(render(aggregate(rows, m, a.by), a.by))
    if a.diff:
        print()
        print(diff_last_two_weeks(rows, m, a.by if a.by != "week" else "overall", a.bonferroni))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
