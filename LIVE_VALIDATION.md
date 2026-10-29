# Receipt — live validation

Checked October 28–29, 2026, Denver time. No paid model calls were made.

## Verified against the actual Qloo service

- The saved server-side key authenticates against the hackathon host.
- Kendrick Lamar and Everything Everywhere All at Once resolve as distinct anchors.
- Work & Class and Tavernetta resolve to Denver places.
- An unscoped city workflow scored all 52 comparison places, including agent picks.
- A 5,000-metre Mission Ballroom workflow scored all 51 comparison places.
- Personalized scoring, omission scoring and pagination keep the full ID set.
- A constructed list produced supported, mismatch and unverified outcomes.
- A changed list passed a new audit over the same frozen comparison set.
- Explicit confirmation issued a receipt tied to the exact passing evidence hash.
- Actual Chrome checks pass at 1440px and 390px: live audit, changed-list audit,
  confirmation/download, real-data rules-based agent, and four-capture live batch.
- The batch inputs were hand-entered validation lists, not model captures.
- A passing initial agent draft stopped after one round; no correction was fabricated.
- An ambiguous film anchor caused an evidence-incomplete hold, not a passing claim.

Private reports and screenshots are in ignored data/. Raw provider responses and
credentials are not included in public source. Derived counts here describe
specific validation runs, not a general accuracy or personalization benchmark.

## Live differences corrected

| Difference | Fix |
|---|---|
| Quality-sorted references included six places without personalized scores | Use taste-independent city discovery; preserve the complete-coverage requirement |
| Insights places use type=urn:entity and subtype=urn:entity:place | Read the specific subtype when available |
| Search rejects WKT on the hackathon service despite newer documentation | Send latitude,longitude to Search; retain longitude-first WKT for Insights |
| The optional model selector had malformed option markup | Separate source options and address them by value |
| Related graph tags could be mistaken for personal traits | Show declared anchors and computed omission evidence |
| An unavailable generic metric appeared as zero in profile rows | Show unavailable cells instead of zero |
| Deployment rsync would include private video frames | Exclude the video kit/output and voiceover notes explicitly |

## Baseline finding

The no-interest query returns entities but no affinity values. The numeric baseline
check therefore fails. Authentication success does not validate this metric.
QLOO_BASELINE_VERIFIED remains 0. Taste Lift and generic rate remain unavailable
for these live runs. Popularity and quality were not substituted for affinity.

Standard can support a place by its personalized rank alone and says so.
Verified-only requires a baseline and therefore holds results when it is absent.

## Agent sources

- qloo: highest returned business ratings in the comparison pool plus explicit
  revision rules; no LLM and no claim that ratings measure popularity.
  It follows city/category/radius, does not interpret free-text task notes, and
  rechecks any changed list with the same evaluator.

## Audit changes — v0.5.0, October 29

- Fixed the agent view hiding tastes instead of proposed places. Browser checks
  now assert editable tastes and hide the irrelevant synthetic-source checkbox.
- Added validated Qloo images, addresses, venue metadata and per-input contribution
  scores. Only HTTPS images.qloo.com image URLs are accepted; missing images degrade.
- Added one-click revision retaining supported picks, per-round ranks/statuses,
  visual receipts, a hero live example and stacked profile bars.
- Added separately named Panel lift: personal percentile minus the mean percentile
  of three equally weighted, declared music profiles, over identical IDs/filters.
  All three need complete scores. The curated panel is not population popularity.
- Panel version contrasting-music-v1 was unavailable because Bad Bunny did not
  resolve uniquely. Version v2 substitutes uniquely resolved J Balvin, based on
  resolution availability. Membership was frozen before scoring that version.
- v2 members: Taylor Swift + Beyoncé; Metallica + Iron Maiden; J Balvin + Shakira.
- Distinctive taste requires P60 fit and +10 panel points. An actual Kendrick +
  Everything Everywhere run had one of three generic ratings picks pass; two
  cleared fit but failed this panel bar. A genuine rules revision kept Guard and
  Grace, added Jelly Cafe/Linger and had three of three pass. No failure was planted.
- Actual local Chrome checks pass all three live workspaces at 1440px/390px,
  including one-click preservation, complete panel evidence, images/contributions,
  a two-round rules loop and confirmation/download. These are specific test cases.
- 106 offline tests and the synthetic browser regression pass. Four actual
  ratings-agent first drafts were captured privately; they are not LLM outputs.
- Internal audit/planning documents are now local-only and removed from reachable
  public branch history. Starter tools/replay/page/playbook leftovers were removed.
- Hosted v0.5.0 Chrome checks pass the same live workflows at 1440px and 390px.
  A fresh anonymous public clone contains no internal documents in files/history.
- The release's separate-network check passes actual Qloo flows, complete panel
  evidence, frozen re-audit, confirmation, a two-round ratings agent and batch.
  Fresh install/pip check and 106 tests pass (one upstream TestClient warning).
  [v0.5.0 release verification](https://github.com/woooj02/receipt/actions/runs/40926859918).
- Upload preflight exposed a venv symlink escaping the directory-only exclusion.
  The upload stopped before restart; this app's environment was rebuilt. The
  corrected rule preserves both venv directories/symlinks and excludes env variants.
  An actual rsync fixture regression, redeploy and hosted workflow checks pass.
- A new private 2:10 recording uses actual hosted Qloo evidence and four actual
  ratings-agent control outputs. It is not an LLM study and has not been uploaded.
- scripted: synthetic catalog and deterministic workflow example.
- live: optional model adapter; requires a separate key, model and spending permission.

## Public release verification — October 29

- Approved deployment: https://receipt.91.99.162.43.sslip.io/.
- Public source: https://github.com/woooj02/receipt; anonymous access and GitHub's
  MIT licence detection pass. The repository About section links the live app.
- Native ARM64 Python service runs behind nginx with a valid HTTPS certificate.
  Only the supplied Qloo key was configured; .env is owner-only and not served.
  Model permission and model-call allowance are both zero.
- Hosted Chrome checks pass at 1440px and 390px: audit, frozen revision,
  exact-snapshot confirmation/download, rules-agent and four-capture batch.
  HTTPS session cookies are Secure, HttpOnly and SameSite=Strict.
- Direct TLS from the laptop failed; browser checks used an SSH SOCKS proxy with
  certificate verification enabled. This was not used as proof of public access.
- A separate GitHub-hosted Ubuntu runner then reached the app over public HTTPS
  without credentials or that proxy. It passed health, private-path denials, live
  audit, frozen revision, confirmation, rules-agent and two-profile batch checks.
- That runner installed a fresh public checkout, passed pip check and all 92
  offline tests. [Reproducible release run](https://github.com/woooj02/receipt/actions/runs/40829311653).
- The hosted input lists were constructed validation cases, not model captures.
  The check logs expose pass/count summaries, not raw provider responses or tokens.

## Remaining evidence and submission work

A real LLM capture study and preference/customer validation are not completed.
Final Devpost submission has not been performed and needs separate approval.
Docker image build verification remains unavailable because local socket access is denied.
