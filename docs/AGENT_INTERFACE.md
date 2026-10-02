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
