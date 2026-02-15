# Shipnote

Shipnote turns meaningful git commits into queued, reviewable draft posts.

It runs locally, monitors one repository at a time, and writes markdown drafts to:

- `.shipnote/queue`

Shipnote never auto-posts.

## Install

```bash
pipx install shipnote
```

## Quick Start

1. Add secrets:

```bash
mkdir -p ~/.shipnote
chmod 700 ~/.shipnote
cat > ~/.shipnote/secrets.env <<'ENV'
# Preferred aliases:
SHIPNOTE_API_KEY=...
# optional: openai (default) or anthropic
# SHIPNOTE_PROVIDER=openai
# optional model override:
# SHIPNOTE_MODEL=claude-sonnet-4-5-20250929
#
# Direct provider keys also supported:
# OPENAI_API_KEY=...
# ANTHROPIC_API_KEY=...
# optional:
# AXIS_DEFAULT_MODEL=claude-sonnet-4-5-20250929
ENV
chmod 600 ~/.shipnote/secrets.env
```

2. In any project repo:

```bash
shipnote launch --repo .
```

If the folder is not a git repo yet:

```bash
shipnote launch --repo . --init-git
```

## Commands

```bash
shipnote init --repo .
shipnote launch --repo .
shipnote run-once --config .shipnote/config.yaml
shipnote start --config .shipnote/config.yaml
shipnote check --config .shipnote/config.yaml
shipnote status --config .shipnote/config.yaml
shipnote reset --config .shipnote/config.yaml
shipnote ask --config .shipnote/config.yaml "what's in queue?"
shipnote chat --config .shipnote/config.yaml

# config management
shipnote config --config .shipnote/config.yaml list
shipnote config --config .shipnote/config.yaml get queue_dir
shipnote config --config .shipnote/config.yaml set queue_dir ".shipnote/custom-queue"
shipnote config --config .shipnote/config.yaml set content_policy.focus_topics '["python tooling","developer systems"]'
shipnote config --config .shipnote/config.yaml unset context.additional_files
```

### Command Reference

- `shipnote init --repo .`: Bootstrap `.shipnote/` config and default templates for a repository.
- `shipnote launch --repo .`: Bootstrap (if needed), run setup checks, then start the daemon loop.
- `shipnote start --config ...`: Start the daemon loop using an existing config.
- `shipnote run-once --config ...`: Process new commits a single time and exit.
- `shipnote check --config ...`: Validate config, git repo state, secrets, and templates.
- `shipnote status --config ...`: Show daemon/runtime state and queue processing counters.
- `shipnote reset --config ...`: Reset state tracking (`last_commit_sha`, counters, processed commits).
- `shipnote ask --config ... "<question>"`: Ask the operator assistant a single question.
- `shipnote chat --config ...`: Start an interactive operator chat session.

### Config Command Reference

- `shipnote config ... list`: Print the full config file.
- `shipnote config ... get <key>`: Print a config value by dot-path key.
- `shipnote config ... set <key> <value>`: Set a config key (supports scalars and JSON for lists/objects).
- `shipnote config ... unset <key>`: Remove a config key.

## Config Highlights

Generated config includes:

- `context.additional_files` and `context.max_total_chars`
- `content_policy.focus_topics`
- `content_policy.avoid_topics`
- `content_policy.engagement_reminder`

Additional context files are loaded from `.shipnote/` only and currently support `.md` and `.txt`.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip build twine
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```
