# Shipnote

Shipnote turns meaningful git commits into queued, reviewable build-in-public draft posts.

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
OPENAI_API_KEY=...
# or ANTHROPIC_API_KEY=...
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
shipnote check --config .shipnote/config.yaml
shipnote status --config .shipnote/config.yaml
shipnote ask --config .shipnote/config.yaml "what's in queue?"
shipnote chat --config .shipnote/config.yaml
```

## Development

```bash
python -m venv .venv
.venv/bin/pip install -U pip build twine
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```
