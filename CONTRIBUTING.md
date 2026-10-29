# Contributing

This repo compares LLM trackers by the sample they collect and what that sample costs. The most useful contribution is a corrected plan fact with a link to the vendor page that shows it.

## Change the data, then regenerate

1. Edit [tools.yaml](tools.yaml). Each entry describes the entry plan only.
2. Set `answers_basis` to say how monthly answers can be derived:
   * `stated` when the vendor publishes an answer or scan cap, with the number in `answers`
   * `computed` when `prompts`, `engines` and a daily or weekly `refresh` are all public
   * `credits` when the vendor publishes both `credits` and `credits_per_answer`
   * `unknown` when none of those hold. Leave it unknown rather than guessing.
3. Never type answers per month, cost per 1,000 answers or the noise column. `render_table.py` computes them.
4. Run `python render_table.py --write`, then `python render_table.py --check`.
5. Open a pull request with the vendor link.

## Accepted

* Price, plan, prompt, engine or refresh changes with a source link.
* A published collection method (interface or API) for a tool marked `Not published`.
* A new tool, if its pricing page lets at least one of the three bases above be filled in.

## Not accepted

* Affiliate or tracking links.
* Review scores and star ratings.
* Currency conversions. Keep the currency the vendor publishes.

## Code

`llmvis` is standard library only and must run on Python 3.9. New statistics go in `stats.py` with a test that checks a known reference value. Parsing and matching go in `score.py`. If you change the sample log generator, rerun it and keep the planted Perplexity jump, because a test depends on it.

```bash
pip install pyyaml
python render_table.py --check
python -m unittest discover -s tests -v
python examples/make_sample.py
```
