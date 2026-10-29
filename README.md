# Receipt

Cultural quality checks for recommendation agents.

Receipt evaluates proposed places against cultural tastes, explains rank sensitivity,
returns a structured critique, and checks the agent's revision. Its test suite
compares captured recommendations across taste profiles using one frozen universe.

**Status:** real Qloo audits, radius checks, revisions, receipts and rules-based
agent runs work locally. The city-only affinity baseline is unavailable; Taste
Lift stays disabled. Optional LLM runs, external hosting and publication are pending.

For the complete purpose, decisions, formulas, limitations and audit questions,
read [project.md](project.md).

## Run locally

Requires Python 3.12. From a fresh checkout:

```bash
./run.sh setup
cp -n .env.example .env
./run.sh
```

Open http://127.0.0.1:8132. Without a Qloo key the evaluator uses an explicitly
labelled synthetic catalog. **Load synthetic sample** always uses synthetic evidence.
With a key, **Run live Denver example** uses real Qloo evidence for a hand-entered
list near Mission Ballroom. The list is not a captured model response.

## Three workspaces

1. **Audit a list:** 2–5 anchors, 1–6 places, a city, policy, restaurant category,
   and optional venue coordinates/radius. Every place stays in the result.
2. **Watch an agent revise:** proposal → critique → revision → new audit. Choose
   a live Qloo discovery agent with explicit rules and no LLM, the labelled
   synthetic demonstration, or a separately configured model. Up to three rounds;
   a passing first draft stops immediately. The rules agent follows structured
   city/category/radius constraints and does not interpret free-text task notes.
3. **Test an agent:** import captured-output JSON or load the 20-capture synthetic
   sample. Inspect metrics, repeat controls, per-profile coverage, and download
   the report. The sample has 10 taste profiles with two captures each.

Passing results can receive explicit browser confirmation and a JSON receipt.
Suggestions and agent-generated scores cannot approve themselves.

## What the evaluator measures

- One comparison set contains up to 50 city reference places plus resolved agent
  choices. Scoring paginates the same complete ID filter.
- All comparison places need finite scores before percentiles are published.
- Batch profiles share that same set. Revisions retain tastes, policy, city,
  category, radius, and universe. A new outside place needs a fresh audit.
- Taste Lift compares personalized and city-only percentiles. It is unavailable
  until live verification supports the baseline and the server explicitly enables it.
- Generic means the place clears fit but fails the configured rank-lift bar.
  It can still be an excellent broadly liked place.
- Anchor removal measures rank sensitivity, not a causal reason for enjoyment.
- Sensitivity is mean pairwise Jaccard distance between supplied recommendation
  sets. Repeat-control variation helps expose model randomness. Neither proves quality.
- Mismatch, unverified, and constraint failures retain all picks in the denominator.

Restaurant tags are resolved through documented tag search, and venue radius
uses straight-line distance from a supplied point. Missing tags or coordinates
stay unverified. Hours, road travel time, safety, price and availability are unknown.
See [Qloo tag search](https://docs.qloo.com/reference/search-tags) and
[Insights parameters](https://docs.qloo.com/reference/insights-api-deep-dive).

## API

POST /api/agent/audit accepts:

```json
{
  "anchors": ["Kendrick Lamar", "Everything Everywhere All at Once"],
  "candidates": ["Official place name", "Another official place name"],
  "city": "Denver, Colorado",
  "policy": "standard",
  "constraints": {"category": "restaurant", "venue": null},
  "demo": false
}
```

Retain the session cookie. Include revision_of with a prior audit_id to test a
changed list. Agent endpoints cannot confirm receipts.

POST /api/agent/run accepts anchors, city, goal, policy, constraints, mode
(scripted, qloo, or live), and max_rounds (1–3). qloo uses actual Qloo discovery
and revision rules without model calls. No result is automatically confirmed.

POST /api/test-suite accepts agent_name, agent_version, prompt_version, a
timezone-aware captured_at timestamp, city, and 2–20 captures in profiles.
Each capture has a unique profile_id, anchors, recommendations, and optional
control_group. Members of a repeat-control group must have identical tastes.
Capture provenance supplied by a caller is explicitly unverified.

For long work, POST the same body to /api/jobs/audit, /api/jobs/agent or
/api/jobs/batch. Poll GET /api/jobs/{job_id}, or POST
/api/jobs/{job_id}/cancel. Jobs are private to the browser session.

## Keys and controlled model use

QLOO_API_KEY enables the live evaluator. Run the private probe before enabling
QLOO_BASELINE_VERIFIED=1. The probe never changes that setting automatically.
Current live probes return no city-only affinity values. Leave the setting at 0;
generic rate and Taste Lift remain unavailable. Standard can check fit alone;
Verified-only holds results without a baseline. See [live validation](LIVE_VALIDATION.md).

Optional model use additionally requires OPENAI_API_KEY, RECEIPT_LLM_MODEL and
RECEIPT_ALLOW_LLM_CALLS=1. These are disabled/blank in the example environment.
Only enable them with authorized API spending. The adapter uses strict JSON
outputs, local validation, a fixed API host, no automatic generation retry, and
bounded rounds. See [official Structured Outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs).

After explicit model configuration, ./run.sh capture --input
examples/study-input.json --repeat 2 records 20 real outputs with repeat controls.
Captured datasets and probe reports go into ignored data/ files with owner-only
permissions. The real Qloo workflow is validated; no real-model study is completed.

## Verification

```bash
./run.sh test
./venv/bin/python scripts/check_browser.py
```

The browser check uses local Chrome/Chromium and an isolated temporary profile.
It checks all three workspaces at 1440px and 390px and makes no provider calls.
Add --screenshots to retain local previews in /tmp.

## Runtime and deployment

Two workers, a four-run queue, 180-second budgets, cancellation, a 128-KB body
limit, per-address work limits and bounded provider retry protect the demo.
The private Qloo cache holds up to 512 entries for five minutes.
Per-process daily provider ceilings reset on process restart; they are not a
substitute for persistent provider-side billing limits.

Use one server process: audit ownership, confirmation tokens, queues and budgets
are in memory. Audits expire after 30 minutes. Confirmation records an explicit
action and evidence hash; reviewer identity is not authenticated.

deploy.sh prepares the existing Hetzner host and checks HTTPS after deployment.
Dockerfile provides a separate non-root single-worker recipe. No deployment has
been run. Local Docker socket access was denied, so the image is not build-verified.
See [PREKEY_HANDOFF.md](PREKEY_HANDOFF.md) for the live gate and release status.

## License

MIT. See [LICENSE](LICENSE).
