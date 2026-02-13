# AGENTS.md

Guidance for AI/code agents working in this repository.

## Project Summary

`shipnote` is a Python CLI daemon that watches git commits and generates queued markdown drafts for build-in-public posting.

- Package: `shipnote`
- Entry point: `shipnote.cli:main`
- Runtime output: `.shipnote/queue/*.md`
- Core model dependency: `axis-core`

## Local Environment

Use a local virtual environment in this repo.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install -e .
```

Verify `axis-core` resolves from venv site-packages (not a local editable checkout):

```bash
.venv/bin/python -c "import axis_core; print(axis_core.__file__)"
```

Expected path prefix:
`/Users/xavierhillman/blackbox/code/shipnote/.venv/lib/python.../site-packages/...`

## Common Commands

Run tests:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Build/package checks:

```bash
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

CLI usage examples:

```bash
.venv/bin/shipnote init --repo .
.venv/bin/shipnote check --config .shipnote/config.yaml
.venv/bin/shipnote run-once --config .shipnote/config.yaml
.venv/bin/shipnote start --config .shipnote/config.yaml
```

## Architecture Map

- `shipnote/cli.py`: CLI command routing and user-facing commands.
- `shipnote/process_loop.py`: main polling loop; commit discovery, filtering, context build, generation, queue write, state updates.
- `shipnote/generation.py`: `axis-core` agent prompt + JSON parsing/validation for drafts.
- `shipnote/operator.py`: ask/chat operator interface via `axis-core` with deterministic fallback.
- `shipnote/config_loader.py`: config parsing/validation and secrets loading.
- `shipnote/git_cli.py`: git shell interactions and commit history helpers.
- `shipnote/context_builder.py`: generation payload assembly from repo + state.
- `shipnote/heuristic_filter.py`: skip/keep heuristics for commits.
- `shipnote/secret_scanner.py`: regex redaction of sensitive patterns in diffs.
- `shipnote/queue_writer.py`: queue file naming/frontmatter/body output + ledger updates.
- `shipnote/state_manager.py`: atomic state persistence and weekly rollover normalization.
- `shipnote/template_loader.py`: template loading/validation.
- `shipnote/scaffold.py`: bootstrap `.shipnote` directory, config, and templates.

## Data and Runtime Files

Shipnote writes repository-local runtime files under `.shipnote/`:

- `.shipnote/config.yaml`
- `.shipnote/state.json`
- `.shipnote/runtime.lock`
- `.shipnote/daemon.json` (status)
- `.shipnote/templates/*.md`
- `.shipnote/queue/*.md`

Global secrets file:

- `~/.shipnote/secrets.env` (must be mode `600`)

Provider key requirements:

- At least one of `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` must be set in secrets.
- Optional model override: `AXIS_DEFAULT_MODEL`.

## Engineering Guardrails

- Preserve atomic write behavior (`*.tmp` + replace) in state and queue writers.
- Preserve lock usage (`exclusive_lock`) around stateful loop/reset operations.
- Keep `state.json` backward-compatible; normalize unknown/missing fields defensively.
- Do not reduce redaction safety when changing `secret_scanner` or config pattern handling.
- Keep CLI commands stable unless a change is requested.
- Keep generated queue frontmatter keys stable; external workflows may depend on them.

## Testing Expectations for Changes

When changing behavior in `shipnote/*`, do both:

1. Update/add focused unit tests in `tests/`.
2. Run full unittest discovery before concluding work.

Minimum targeted mapping:

- `state_manager.py` changes -> `tests/test_state_manager.py`
- `heuristic_filter.py` changes -> `tests/test_heuristic_filter.py`
- `secret_scanner.py` changes -> `tests/test_secret_scanner.py`
- `queue_writer.py` changes -> `tests/test_queue_writer.py`
- `git_cli.py` changes -> `tests/test_git_cli.py`
- scaffold/bootstrap changes -> `tests/test_scaffold.py`

## Notes for Agents

- Prefer small, explicit patches over broad refactors.
- Keep dependencies minimal; this project currently uses stdlib + `axis-core`.
- If introducing new config keys, validate in `config_loader.py` and document defaults.
- If new behavior touches queue output or state format, include migration-safe handling.
