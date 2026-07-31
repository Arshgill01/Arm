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

Outbound notification is operational. The installed stack has no inbound poller,
webhook, user service, or scheduled receiver; its only Telegram `getUpdates` use
is setup-time discovery. Replies therefore do not reach Codex today. Until the
bridge is implemented and tested, alerts are one-way and decisions return through
the Codex thread.

Any bidirectional implementation must:

- keep the bot token outside Git;
- authenticate the permitted chat/user ID;
- avoid exposing a public unauthenticated command endpoint;
- persist an auditable decision ID and timestamp;
- support a small allow-list of responses rather than arbitrary shell commands;
- tolerate duplicate Telegram updates; and
- fall back cleanly to the Codex thread.

## Secure bridge design

Use Telegram long polling with the existing Codex app-server. The managed daemon
already exposes a mode-0600 Unix control socket and the supported transport
helper is `codex app-server proxy --sock <socket>`. This keeps Telegram decisions
inside the same live thread instead of launching a competing `codex exec resume`
process.

`codex-decision ask` should capture the exact `CODEX_THREAD_ID`, create an opaque
one-time decision token, persist the mapping in a mode-0600 SQLite database, and
send two or three inline callback buttons. Callback data contains only the token
and option number, never a thread UUID or command.

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

The first implementation should reject mid-turn steering and arbitrary free-form
messages. A later, separately tested version can evaluate app-server item
injection.
