# Real ratings-agent check, October 29

**Same three highly rated restaurants; ten taste profiles; 12 of 30 picks
cleared Receipt's Distinctive taste setting.**

This is a real Qloo run of the generic ratings rules agent. It is not an LLM
benchmark. The agent intentionally ignores tastes and selects the three highest
returned business ratings in its local discovery pool; ratings aren't popularity.

| Outcome | Picks | Share of all 30 |
|---|---:|---:|
| Cleared the declared setting | 12 | 40% |
| Good fit, insufficient lift versus the declared panel | 10 | 33.3% |
| Weak taste match | 5 | 16.7% |
| Couldn't verify | 3 | 10% |

All ten profiles remain in the report. Nine had complete scores for all 50
comparison places; the soul/television profile had unresolved taste evidence
and its three picks stayed unverified. We didn't drop it or substitute a
better-performing profile. Zero output variation is expected from these rules.

| Declared input profile | Passed | Low panel lift | Weak match | Unverified |
|---|---:|---:|---:|---:|
| Rap/cinema | 1 | 2 | 0 | 0 |
| Pop | 2 | 1 | 0 | 0 |
| Jazz | 1 | 0 | 2 | 0 |
| Soul/television | 0 | 0 | 0 | 3 |
| Alternative | 2 | 1 | 0 | 0 |
| Latin/animation | 1 | 2 | 0 | 0 |
| Jazz/rock | 1 | 1 | 1 | 0 |
| Electronic | 2 | 1 | 0 | 0 |
| Country | 1 | 1 | 1 | 0 |
| Experimental | 1 | 1 | 1 | 0 |

## Method

The [exact input cohort](../examples/ratings-study.json) was saved before any
target scores were inspected. Every profile used one shared 50-place comparison
set, restaurant category, and a 5,000 m radius around Mission Ballroom, Denver.
Captured at 2026-10-29 23:18:19 UTC. Cohort SHA-256:
`499376e66a6561225ca2e211993f77dff9cb377af2173fe1337bf8cb1d022f19`.

The declared setting requires taste rank ≥ P60 and panel lift ≥ 10 percentile
points. The three equally weighted reference profiles are Taylor Swift + Beyoncé,
Metallica + Iron Maiden, and J Balvin + Shakira. Their verified IDs are pinned
in `contrasting-music-v3-pinned`; no profile is discarded on a failed request.
This panel isn't a representative crowd. Overlap is disclosed, not removed.

Run locally with your own Qloo key exported in the environment:

```bash
./venv/bin/python scripts/ratings_study.py
```

This bypasses the hosted app's allowance but still uses the provider's quota
and local call pacing. Captures and provider evidence are written privately to
ignored `data/`; this page contains derived counts, not a response-data dump.

Ten curated profiles, one venue, one negative-control rules agent and repeated
picks are not independent samples. Thresholds need calibration. These counts
describe our evaluator's decisions, not people's enjoyment, city popularity,
buyer demand or evidence that an LLM performs worse than Receipt.
