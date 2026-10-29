import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llmvis import score, stats  # noqa: E402


class StatsTests(unittest.TestCase):
    def test_wilson_matches_reference(self):
        lo, hi = stats.wilson(9, 30)
        self.assertAlmostEqual(lo, 0.1666, places=3)
        self.assertAlmostEqual(hi, 0.4788, places=3)

    def test_wilson_zero_successes_is_not_degenerate(self):
        lo, hi = stats.wilson(0, 4)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.4)

    def test_wilson_rejects_bad_counts(self):
        with self.assertRaises(ValueError):
            stats.wilson(5, 4)

    def test_samples_needed(self):
        self.assertEqual(stats.samples_needed(0.30, 0.10), 356)
        self.assertGreater(stats.samples_needed(0.30, 0.05), 1300)

    def test_compare(self):
        diff, p = stats.compare(9, 30, 17, 30)
        self.assertAlmostEqual(diff, 8 / 30)
        self.assertLess(p, 0.05)
        self.assertEqual(stats.compare(0, 0, 1, 2), (0.0, 1.0))


class ScoreTests(unittest.TestCase):
    cfg = {"brand": "Lumora", "aliases": ["Lumora", "lumora.io"], "domains": ["lumora.io"],
           "competitors": {"Orbitly": ["Orbitly"], "Orbit": ["Orbit"]}}

    def test_word_boundaries(self):
        m = score.Matcher(self.cfg)
        s = m.score({"text": "Try Orbitly or Lumora.", "sources": []})
        self.assertTrue(s["mentioned"])
        self.assertEqual(s["rivals"], ["Orbitly"])
        self.assertFalse(m.score({"text": "Lumoracle is unrelated", "sources": []})["mentioned"])

    def test_citation_matches_subdomains_only(self):
        self.assertTrue(score.cites(["https://www.lumora.io/a"], ["lumora.io"]))
        self.assertTrue(score.cites(["https://docs.lumora.io/a"], ["lumora.io"]))
        self.assertFalse(score.cites(["https://notlumora.io/a"], ["lumora.io"]))

    def test_share_of_voice(self):
        m = score.Matcher(self.cfg)
        rows = [{"date": "2026-10-01", "engine": "x", "text": "Lumora and Orbitly", "sources": []},
                {"date": "2026-10-01", "engine": "x", "text": "Orbitly only", "sources": []}]
        g = score.aggregate(rows, m, "overall")["all"]
        self.assertEqual((g["n"], g["mentions"], g["brand_slots"], g["all_slots"]), (2, 1, 1, 3))

    def test_csv_and_jsonl_load_the_same(self):
        row = {"date": "2026-10-01", "engine": "chatgpt", "prompt": "p", "text": "Lumora",
               "sources": ["https://lumora.io"]}
        with tempfile.TemporaryDirectory() as d:
            j = Path(d, "a.jsonl")
            j.write_text(json.dumps(row) + "\n", encoding="utf-8")
            c = Path(d, "a.csv")
            c.write_text("date,engine,prompt,text,sources\n2026-10-01,chatgpt,p,Lumora,https://lumora.io\n",
                         encoding="utf-8")
            self.assertEqual(score.load_answers(j)[0]["sources"], score.load_answers(c)[0]["sources"])

    def test_sample_log_has_planted_perplexity_jump(self):
        rows = score.load_answers(ROOT / "examples" / "answers.example.jsonl")
        self.assertEqual(len(rows), 672)
        out = score.diff_last_two_weeks(rows, score.Matcher(score.load_brand(ROOT / "examples" / "brand.example.json")), "engine")
        self.assertRegex(out, r"perplexity .* CHANGE")


if __name__ == "__main__":
    unittest.main()
