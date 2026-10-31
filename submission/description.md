# Receipt

**Claude's own dinner picks: 0 of 3 cleared Receipt. After two revisions: 3 of 3.**

AI concierges confidently recommend places that ignore who you are.
Receipt checks those recommendations before they reach a customer.

## Watch it happen

A Nina Simone + David Bowie fan wants dinner near Mission Ballroom in Denver.
A real local Claude client independently proposes three places, then calls
Receipt through MCP. Live Qloo evidence finds one weak taste match, one
unresolved name and one category rejection. None clear the recorded standard.

Claude reads the critique and changes its list. Two picks clear the next check;
the third still cannot be verified. It keeps those two, replaces only the third,
and all three clear the final audit over the same tastes, radius and comparison set.
Receipt returns **Ready for review**. Confirmation still waits for the user.

No failing draft was planted and no score was edited. The model runs in the
user's existing local client; no model credentials run on our server. This is one
real integration example, not a controlled LLM benchmark.
[Connect your own AI and inspect the method](https://github.com/woooj02/receipt/blob/master/docs/mcp.md).

## Why Qloo makes the difference

A business rating tells you a place is well liked. Qloo connects the person's
music, films and other interests to actual place affinities. Receipt resolves
the names, checks category and venue radius, and scores the identical place IDs
for the person, three declared reference profiles and omitted-taste comparisons.

The cards show real place images, addresses, provider-reported contributions
and computed rank sensitivity. A high taste rank with little panel lift remains
visibly different from a recommendation that stands out for this profile.

The panel is a declared comparison, not a population. Panel lift means personal
percentile minus the mean percentile of Taylor Swift + Beyoncé, Metallica +
Iron Maiden, and J Balvin + Shakira on the same place set.

In a separate live-Qloo study, **18 of 30 top-rated picks didn't clear our
Distinctive taste standard** across ten curated profiles. Ten fit but lacked
panel lift, five had weak matches and three couldn't be verified. Nine profiles
had complete affinity coverage; the unresolved profile remains in the report.
This was an actual taste-blind ratings rules agent, not an LLM benchmark.
The [full cohort and method](https://github.com/woooj02/receipt/blob/master/docs/ratings-study.md) show every outcome.

## Who would use it

Ticketing and concierge platforms can check pre-show dinner suggestions before
sending them to fans. Travel teams and AI app developers can audit existing
recommendation agents through the HTTP API. Operators use the workbench to inspect
the critique, test changed lists and issue a visual receipt for a reviewed result.

The batch workspace runs the same checks over captured outputs and shows a
report card with per-profile bars, output variation, panel lift and coverage.
It keeps every submitted pick visible, including unknown names and incomplete evidence.

## What we built

Python/FastAPI and Pydantic validate inputs and run bounded, session-owned jobs.
Plain JavaScript renders three complete workspaces: list audit, agent revision
and captured-output testing. Deterministic code handles ranks, policies,
scope checks, frozen revisions and exact-snapshot confirmation.

The live ratings agent starts with business ratings and applies explicit revision
rules after receiving Receipt's critique. An optional model adapter lets a real
LLM propose and revise separately; model execution is disabled on this hosted demo.
An existing agent can call Receipt through its local MCP bridge without adopting that adapter.
Its existing model access supplies the language generation; Receipt needs no
extra LLM key to audit that agent's proposals.

The application builds on a local FastAPI starter. Receipt's evaluator, location
checks, reference panel, agent loop, review flow and report workspaces are the
project implementation.

## What we verified

Live Qloo scoring, provider contributions, images and addresses, venue-radius
checks, same-set revisions, explicit confirmation and receipt download work.
Desktop and phone browser journeys cover all three workspaces. Regression tests
cover missing/ambiguous evidence, complete coverage, pagination, reference-panel
failures, revision freezing, ownership, stale confirmations and provider errors.

## What we don't claim

Ranks and panel lift do not guarantee enjoyment. Our three curated music profiles
are not a representative crowd; the thresholds need calibration. A passing
revision is another check by the same evaluator, not proof of better choices.

The original no-interest city baseline has no affinity values, so its Taste Lift
and population-style generic-rate claims remain unavailable. Panel lift is separately
named. No real LLM benchmark, buyer demand or preference validation is claimed.
Hours, bookings, safety, accessibility and road travel time are not verified.
A receipt records an action and evidence hash; it does not authenticate identity.

## Try it

- App: https://receipt.91.99.162.43.sslip.io/.
- Demo video: https://youtu.be/h0lgcsNLXpg.
- Public MIT source: https://github.com/woooj02/receipt.
- Walkthrough: https://github.com/woooj02/receipt/blob/master/submission/testing-instructions.md.
