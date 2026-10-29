# Receipt

## Tagline

Cultural quality checks for recommendation agents.

## What it does

Receipt helps engineers inspect whether an agent's place recommendations are
supported for a person's stated tastes. It evaluates proposed places using Qloo,
returns a structured critique, checks a revised list, and records an explicitly
reviewed result. A batch workspace compares captured recommendation lists across
taste profiles using one frozen comparison set.

## Who it is for

Engineers building AI concierge and discovery products, and operators reviewing
their recommendations. An ordinary customer would usually receive the result
inside the company's existing app. Receipt's workbench exposes the checks and
evidence for the engineer or reviewer.

## A concrete example

An agent proposes dinner near a concert venue in Denver. The reviewer supplies
two or more stated favourites, proposed restaurants and a venue radius.
Receipt resolves the entities, verifies returned category/location metadata and
compares the proposals with a taste-independent city reference pool.
It holds weak or unverified picks and suggests alternatives. A changed list must
be audited again before the reviewer can confirm and download its receipt.
The live example is hand-entered and labelled; it is not presented as a model capture.

## What Qloo powers

The running application uses Qloo Search, tag lookup and Insights for entity
resolution, restaurant categories, location-constrained discovery, personalized
affinity and repeated scoring with one taste omitted.
The comparison IDs stay identical across profile and omission scoring.
Missing or ambiguous evidence remains visible rather than becoming a zero score.

## The three workspaces

1. Audit a list: inspect each pick, its relative fit, location checks and evidence.
2. Watch an agent revise: a bounded proposal, critique and re-audit workflow.
   The Qloo discovery agent uses actual data and explicit rules, without an LLM.
   Synthetic and optional model sources are labelled separately.
3. Test an agent: import captured outputs, inspect output variation and
   Qloo-relative failure/coverage measures, then download a report.

## How we built it

Python/FastAPI and Pydantic provide validated APIs and session-owned background
jobs. Plain JavaScript renders the workbench. Deterministic code handles ranking,
coverage, policies, scope checks, confirmation and fingerprints.
The model adapter is optional; an existing agent can use the HTTP audit endpoint.
The application builds on a local FastAPI starter. The Receipt-specific evaluator,
scope checks, review flow and testing workspaces are the project implementation.

## What we verified

Real Qloo audit, venue-radius checks, changed-list audit and receipt confirmation
work in the hosted HTTPS application. Chrome checks cover desktop and phone
layouts, including the real-data rules-based agent and imported-list batch workspace.
Offline regression tests cover missing/ambiguous evidence, fixed comparison sets,
pagination, revisions, ownership, stale confirmations and provider failures.

## A finding we kept visible

Qloo's no-interest response did not provide affinity values. The original
city-only Taste Lift baseline could not be established, so live Taste Lift and
generic-rate reporting stay unavailable. Standard checks personalized fit alone;
Verified-only holds results without a baseline.
We did not relabel popularity or quality as affinity to make a metric appear to work.

## What the result establishes

Receipt measures agreement with Qloo evidence under an explicit prototype policy.
It does not guarantee enjoyment. Omission tests show rank sensitivity, not cause.
A passing revision is another check with the same evaluator, not independent
evidence that Qloo's own suggestions are better.
Hours, availability, price, accessibility, safety and road travel time are not checked.
Confirmation records an action and evidence snapshot; reviewer identity is not verified.

## Next

Validate useful choices with people and a real agent-output study, calibrate
policy thresholds, and test an integration with a specific concierge team.

## Submission links

- Hosted application: https://receipt.91.99.162.43.sslip.io/.
- Public repository: https://github.com/woooj02/receipt.
- Testing instructions: submission/testing-instructions.md in the repository.
- English description: this document, matching release v0.4.0.
- License: MIT.
- Video: optional; the existing private recording is a labelled synthetic walkthrough.
- Devpost submission: not yet submitted; final approval is separate.
