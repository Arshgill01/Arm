# Telegram and phone workflow

## Available now

Long unattended work uses the machine-level `codex-notify` command. The local
notification stack reports Telegram as its active transport, and notification
commands returned successfully during kickoff. Phone receipt still needs human
confirmation; successful local exit is not delivery proof.

Safe event types:

```text
codex-notify started  --task "Arm AI optimization challenge" "Short status"
codex-notify progress --task "Arm AI optimization challenge" "Milestone"
codex-notify blocked  --task "Arm AI optimization challenge" "Action needed"
codex-notify done     --task "Arm AI optimization challenge" "Result"
codex-notify failed   --task "Arm AI optimization challenge" "Failure"
```

Never include credentials, private source, tokens, or sensitive command
arguments in alerts.

## Bidirectional decisions

The bounded decision bridge is now implemented by
[`telegram_decisions.py`](telegram_decisions.py) and installed on this machine as
the enabled `arm-telegram-decisions.service` user unit. It uses long polling, so
there is no public webhook or inbound network listener. Private configuration and
SQLite state live outside Git with mode `0600` permissions.

The implementation:

- keeps the existing bot token outside Git;
- requires both the configured private chat ID and originating user ID;
- persists decisions, one-time opaque option tokens, update IDs, and delivery
  state in SQLite;
- accepts only two or three registered inline-button options and ignores
  arbitrary chat text;
- deduplicates Telegram updates and rejects expired or already-used choices;
- queues responses while the exact Codex thread is active;
- marks a delivery ambiguous after a post-send connection failure instead of
  blindly submitting it twice; and
- starts a turn only through the mode-`0600` app-server Unix socket.

Operational commands:

```text
python3 ops/telegram_decisions.py probe
python3 ops/telegram_decisions.py status
python3 ops/telegram_decisions.py ask \
  --question "Choose a path" --option "Path A" --option "Path B"
systemctl --user status arm-telegram-decisions.service
```

The first live canary was sent on July 31. Its reply remains a user choice: the
bridge does not interpret lack of response as consent.

## Secure bridge design

Use Telegram long polling with the existing Codex app-server. The managed daemon
already exposes a mode-0600 Unix control socket. Its Unix transport is WebSocket
framed (the `proxy` helper forwards raw bytes; it does not convert JSONL), so the
bridge performs the local WebSocket handshake and then uses the version-matched
`thread/read`, `thread/resume`, and `turn/start` JSON-RPC methods. This keeps
Telegram decisions inside the same live thread instead of launching a competing
`codex exec resume` process.

The setup command captures the exact `CODEX_THREAD_ID`. The `ask` command creates
opaque one-time option tokens and sends two or three inline callback buttons.
Callback data contains only a random token, never a thread UUID or command.

The receiver must:

- allow only the configured private `chat_id` and originating user ID;
- persist/deduplicate Telegram `update_id` and use a monotonically advancing
  offset;
- accept only callbacks tied to an unexpired outstanding decision;
- serialize per-thread delivery and queue replies while a turn is active;
- query exact app-server thread state before starting a turn;
- keep ambiguous post-crash dispatches for manual reconciliation rather than
  blindly submitting twice; and
- inject registered option text only, never interpret chat text as a shell or
  Codex command.

Do not resolve with `--last`: the local Codex session index is incomplete and
does not contain this active thread. The exact environment thread ID is the only
safe routing key.

This first implementation rejects mid-turn steering and arbitrary free-form
messages. A later, separately tested version can evaluate app-server item
injection.
