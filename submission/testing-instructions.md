# Try Receipt

Open https://receipt.91.99.162.43.sslip.io/. No account or API key is needed.
The public demo uses a server-side Qloo key. Model calls are disabled.

## One-minute explanation

An AI concierge gives you restaurant names. Receipt checks whether those names
fit your stated tastes, shows the evidence, and holds weak or unverified choices.
The intended customer is a company building recommendation agents. Its engineers
use this workbench or API; its customers could see a receipt inside the existing app.

## Audit and issue a receipt

1. In **Audit a list**, click **Run live Denver example**. The example uses a
   hand-entered restaurant list, Kendrick Lamar and Everything Everywhere All at
   Once, and a five-kilometre radius around Mission Ballroom.
2. Wait for the progress steps. The result must say **QLOO LIVE**. Inspect the
   comparison coverage, each place's fit, distance, and omitted-taste explanation.
3. Click **Apply suggestions & re-audit** to keep supported picks and test
   replacements. Use **Edit revised list** for manual changes. Suggestions do
   not count as passed until the new audit completes.
4. Run the changed list. Tastes, policy and comparison set stay frozen. If every
   submitted place clears the recorded policy, click **Confirm reviewed result**.
5. Review the visual receipt with place photos and addresses, then expand or
   download its JSON. It records the exact evidence snapshot;
   it does not authenticate the reviewer's identity or guarantee enjoyment.

Actual provider data can change. A hold is a valid result; do not expect every
place or ambiguous taste name to pass. Missing evidence remains visible.

## Watch the agent

Open **Watch an agent revise**, choose the live Qloo rules agent and run the
live example. It starts with the highest business ratings in the comparison pool,
without using tastes, then reads the critique and can
revise for up to three rounds. It stops immediately if its first draft passes.
This mode uses explicit rules, not an LLM; free-text task notes are informational.
It never confirms its own result.

## Test multiple profiles

Open **Test an agent**. The 20-capture sample is explicitly **DEMO — SYNTHETIC**.
It demonstrates report mechanics, not a real-model benchmark. To audit real
outputs, import JSON matching [the captured-output format](../examples/captured-output.json).
That file contains hand-entered inputs for a live Qloo report; it is not model
output. Replace its lists and metadata with genuine captures for an actual study.
The app does not independently verify who generated imported captures.

## Read the limits

Try your own favourites: Dune, Arrival and Little Women show explicit title
choices with media type and year. Select one to continue. Informal `&`/`and`
spellings work; ambiguous place locations still need a narrower venue scope.
A notice explains when your tastes overlap the fixed reference panel.

For a real AI tool flow, [connect your local Claude client](../docs/mcp.md).
The existing client provides model access; Receipt supplies live Qloo checks.
The [ten-profile ratings-agent report](../docs/ratings-study.md) includes all
outcomes and the incomplete profile, rather than treating missing evidence as a pass.

The live example selects **Distinctive taste**: rank ≥ P60 and lift ≥ +10 points
versus a declared three-profile music panel. Open **How the reference panel works**
to inspect its version and members. The panel is not a representative crowd.
**Taste match** checks fit alone. These thresholds are prototype settings.

The current live Qloo no-interest response has no affinity values. Original
**city-only Taste Lift and generic rate are unavailable**, rather than zero.
Panel lift is a separate metric; Verified-only still requires the original baseline.
Hours, prices, reservations,
safety, accessibility and road travel time are not checked.

The synthetic sample remains available if a live run hits a provider or demo
limit. It is labelled separately and never substituted for a failed live run.
Actual release checks are in [LIVE_VALIDATION.md](../LIVE_VALIDATION.md).
