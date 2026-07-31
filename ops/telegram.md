# Telegram and phone workflow

## Available now

Long unattended work uses the machine-level `codex-notify` command. It sends
Telegram notifications when Telegram is configured and otherwise falls back to
ntfy.

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

Outbound notification is already operational. Reply ingestion must be verified
before it is trusted: we need to determine whether the installed notifier exposes
a safe polling/webhook command and how an incoming reply can be scoped to this
repository and active task. Until then, decisions should be treated as one-way
alerts with the response made in the Codex thread.

Any bidirectional implementation must:

- keep the bot token outside Git;
- authenticate the permitted chat/user ID;
- avoid exposing a public unauthenticated command endpoint;
- persist an auditable decision ID and timestamp;
- support a small allow-list of responses rather than arbitrary shell commands;
- tolerate duplicate Telegram updates; and
- fall back cleanly to the Codex thread.

