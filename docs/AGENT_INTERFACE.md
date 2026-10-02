# Read-only NHL paper research interface

An agent with shell access can run these commands from a checkout of master.
Supply a current checkout of the odds-records branch as the archive. Refresh
that checkout with Git before reading; this interface never pulls data itself.
No sportsbook credential is needed or accepted.

```bash
python agent_tool.py status --data-dir ../records/data
python agent_tool.py candidates --data-dir ../records/data
python agent_tool.py player --player-id 8477492 --data-dir ../records/data
python agent_tool.py performance --data-dir ../records/data
```

Each command returns JSON. Status exposes the last recorded run, age, quota and
health; archives older than two hours are marked stale. Candidate and player
reads return up to twenty latest quote observations with book, price, line,
model probability, break-even, estimated return, model version and input hash.
Candidate reads select the latest quote first, then apply its candidate flag,
so a later non-candidate cannot resurrect an older candidate. expired_now is
true when the bookmaker timestamp exceeds ten minutes, is future-dated by more
than one minute, or the game has started. No quote is verified as still available.

Player reads include blocked quotes, model coverage, history counts and reasons.
Performance returns a fixed middle-window paper policy, one decision per
player/game, version-separated calibration and hypothetical returns, pending
outcomes and game-cluster uncertainty. Raw reproducible model inputs remain
in the snapshots; this CLI returns summaries to keep agent context bounded.

## Agent operating contract

- Treat these outputs as timestamped research observations, not trade orders.
- Reject expired, stale or blocked records. Explain uncertainty and missing
  injuries, confirmed deployment and sportsbook rule verification.
- Keep model probability, break-even and the margin-removed market estimate
  distinct. None independently demonstrates a profitable market edge.
- Review the fixed historical study and prospective results before changing
  the sampling policy or model. Never tune against the reserved holdout.
- Make no wagers, send no messages, expose no credentials or increase quota.

This is a CLI contract for a shell-capable agent. A hosted API/MCP service and
an autonomous agent deployment remain separate build tasks.

## Implemented HTTP API and dashboard (2026-10-02)

Run `python review_server.py --data-dir ../records/data` and open
http://127.0.0.1:8765 on the same host. The mobile layout uses responsive cards,
visible focus, plain status text, probability/break-even comparisons, blockers,
model versions, calibrated outcome frequencies, hypothetical returns and quota.
The server binds loopback only, supports GET only, never accepts a credential,
never pulls Git or calls sportsbook endpoints, and never exposes arbitrary files.
Refresh the archive separately. No internet hosting or autonomous agent is active.

| Route | Output |
| --- | --- |
| GET /api/status | Freshness, recorded quota and operational health |
| GET /api/candidates | Latest archived research opportunities, expiry and blockers |
| GET /api/player?player_id=8477492 | Forecast observations including supplemental context |
| GET /api/performance | Version-separated prospective statistical paper results |
| GET /api/research | Historical studies, next frozen protocol, rule-review blockers |
| GET / | Mobile review dashboard |

All successful JSON responses have `Cache-Control: no-store`; errors return
400/404/503. POST is unsupported. The API integration is exercised by real local
HTTP requests in regression tests. Hosting this Python service for access from
a phone/Chromebook needs a host; none has been provisioned or purchased.
