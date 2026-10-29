"""
Sampling math for LLM visibility numbers. Standard library only.

An LLM tracker does not read a ranking. It samples answers and counts how
often your brand shows up, so every visibility score is a proportion k / n
with an error bar that depends almost entirely on n. These helpers make the
error bar visible.

    python -m llmvis.stats ci 9 30                 # 9 mentions in 30 answers
    python -m llmvis.stats compare 9 30 17 30      # week A vs week B
    python -m llmvis.stats plan --baseline 0.30 --lift 0.10
    python -m llmvis.stats plan --baseline 0.30 --lift 0.10 --per-day 90
"""
from __future__ import annotations

import argparse
import math
from statistics import NormalDist

_N = NormalDist()


def z_for(confidence: float) -> float:
    """Two sided critical value, 0.95 -> 1.96."""
    return _N.inv_cdf(0.5 + confidence / 2)


def wilson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials.

    Chosen over the textbook p +/- z*sqrt(p(1-p)/n) because tracker samples
    are small and often sit near 0 or 1, where the textbook interval breaks
    (it returns 0 +/- 0 for 0 of 4 answers).
    """
    if n <= 0:
        return (0.0, 1.0)
    if not 0 <= k <= n:
        raise ValueError(f"k must be within 0..n, got k={k} n={n}")
    z = z_for(confidence)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def half_width(p: float, n: int, confidence: float = 0.95) -> float:
    """Half the Wilson interval width for an observed rate p over n answers."""
    lo, hi = wilson(round(p * n), n, confidence)
    return (hi - lo) / 2


def compare(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """Two proportion z test. Returns (difference p2 minus p1, two sided p value)."""
    if n1 == 0 or n2 == 0:
        return (0.0, 1.0)
    p1, p2 = k1 / n1, k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return (p2 - p1, 1.0)
    z = (p2 - p1) / se
    return (p2 - p1, 2 * (1 - _N.cdf(abs(z))))


def samples_needed(baseline: float, lift: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Answers needed in EACH period to detect baseline -> baseline + lift."""
    p1, p2 = baseline, baseline + lift
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError("baseline and baseline + lift must both be inside (0, 1)")
    za = _N.inv_cdf(1 - alpha / 2)
    zb = _N.inv_cdf(power)
    pbar = (p1 + p2) / 2
    num = za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return math.ceil(num * num / (lift * lift))


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m llmvis.stats", description=__doc__.split("\n\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("ci", help="confidence interval for k mentions in n answers")
    c.add_argument("k", type=int)
    c.add_argument("n", type=int)
    c.add_argument("--confidence", type=float, default=0.95)

    d = sub.add_parser("compare", help="is the move between two periods real")
    for name in ("k1", "n1", "k2", "n2"):
        d.add_argument(name, type=int)

    p = sub.add_parser("plan", help="answers needed to see a given lift")
    p.add_argument("--baseline", type=float, required=True, help="current rate, 0.30 for 30%%")
    p.add_argument("--lift", type=float, required=True, help="change to detect, 0.10 for 10 points")
    p.add_argument("--power", type=float, default=0.8)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--per-day", type=int, help="answers your plan collects per day (prompts x engines)")

    a = ap.parse_args(argv)
    if a.cmd == "ci":
        lo, hi = wilson(a.k, a.n, a.confidence)
        print(f"{_pct(a.k / a.n if a.n else 0)} observed, {int(a.confidence * 100)}% interval {_pct(lo)} to {_pct(hi)}")
    elif a.cmd == "compare":
        diff, pv = compare(a.k1, a.n1, a.k2, a.n2)
        verdict = "likely a real change" if pv < 0.05 else "inside the noise"
        print(f"{100 * diff:+.1f} points, p = {pv:.3f}, {verdict}")
    else:
        n = samples_needed(a.baseline, a.lift, a.alpha, a.power)
        print(f"{n} answers per period to detect {_pct(a.baseline)} -> {_pct(a.baseline + a.lift)} "
              f"at alpha {a.alpha} and power {a.power}")
        if a.per_day:
            print(f"at {a.per_day} answers a day that is {math.ceil(n / a.per_day)} days per period, "
                  f"pooled across prompts and engines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
