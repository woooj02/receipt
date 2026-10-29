# Use Receipt from your own AI

Receipt supplies the Qloo check. Your local Claude client supplies the model.
The bridge uses the official MCP Python SDK over stdio and keeps one private
HTTP session for the audit and its revisions. No model key belongs on our server.
Your existing AI subscription or provider allowance still applies.

From a clone of this repository, with Python 3.12 and Claude Code installed:

```bash
./run.sh setup
./venv/bin/python -m pip install -r requirements-mcp.txt
claude mcp add --transport stdio receipt -- \
  "$PWD/venv/bin/python" "$PWD/scripts/receipt_mcp.py"
```

That calls the public hosted Receipt app. To check against your own local app,
append `--base-url http://127.0.0.1:8132` to the bridge command. Only your own
local app needs its Qloo key; the bridge never reads .env or model credentials.
Claude Desktop and other stdio clients can use the same command and arguments
in their MCP server configuration. Restart the client after configuring it.

Try this prompt:

> I love Nina Simone and David Bowie. Suggest three restaurants before a show
> at Mission Ballroom, Denver, within 5 km of 39.776204, -104.969168. Give your
> own picks first, then use Receipt's Distinctive taste check. Read the critique,
> revise weak picks and re-audit, for at most three rounds. Ask me to choose any
> ambiguous favourite. Don't book or approve anything; check hours separately.

The tools are:

| Tool | Action |
|---|---|
| `resolve_tastes` | Return matching identities, types and years; ask the user if ambiguous |
| `audit_recommendations` | Check the proposed list with the chosen tastes, scope and strictness |
| `revise_recommendations` | Check changed candidates while freezing the original context |

An explicit selection is an input-name → returned entity-ID mapping in
`anchor_selections`. The API checks that the ID belongs to that name's options.
Revisions cannot switch or remove a selection. Similar titles are never
automatically chosen. `&`/`and` and a leading `the` are accepted aliases; a
collision stays ambiguous. Identical place names can refer to different sites:
use the venue-radius filter to narrow them, rather than assuming one location.

Only the browser review flow can confirm a result. There is no approval MCP tool.
Suggestions require another audit; a passing re-audit uses the same evaluator.

## Recorded real-client check

On October 29, a local Claude client independently proposed Hop Alley, Safta and
Super Mega Bien for Nina Simone + David Bowie near Mission Ballroom. It called
Receipt's live Qloo tools: 0/3 passed. Its next list passed 2/3, and its third
passed 3/3. The final picks were Globe Hall Live Music and BBQ, Mercury Cafe and
The Weathervane Cafe. The client kept the same comparison fingerprint and scope.

This is one integration run, not a blinded comparison or a model benchmark.
The first development run was interrupted by server reloads; the successful
run used a stable server. No failure was planted and no scores were edited.
Hours, dinner suitability and booking availability remain separate checks.

Protocol and setup: [MCP SDK](https://github.com/modelcontextprotocol/python-sdk),
[Claude Code MCP](https://code.claude.com/docs/en/mcp).
