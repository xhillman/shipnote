from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shipnote.config_loader import (
    AXIS_MODEL_KEY,
    default_global_defaults_path,
    load_repo_config,
    load_secrets,
)
from shipnote.errors import ShipnoteConfigError, ShipnoteSecretsError


def _run(repo: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write_config(repo: Path, body: str) -> Path:
    cfg_dir = repo / ".shipnote"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _base_config_text() -> str:
    return """
project_name: "Demo"
project_description: "Demo description"
voice_description: "Direct and technical"

poll_interval_seconds: 60
max_drafts_per_commit: 3
lookback_commits: 10

template_dir: ".shipnote/templates"
queue_dir: ".shipnote/queue"
archive_dir: ".shipnote/archive"

context:
  additional_files:
    - ".shipnote/context.md"
    - ".shipnote/notes.txt"
  max_total_chars: 12000

content_policy:
  focus_topics:
    - "software engineering"
    - "developer tooling"
  avoid_topics:
    - "politics"
    - "sports"
  engagement_reminder: "Engage in relevant community discussions before and after posting."

skip_patterns:
  messages:
    - "^wip"
  files_only:
    - "*.lock"
  min_meaningful_files: 1

content_balance:
  authority: 30
  translation: 25
  personal: 25
  growth: 20

secret_patterns:
  - "(sk-[a-zA-Z0-9]{20,})"
""".strip()


class ConfigLoaderTests(unittest.TestCase):
    def test_load_repo_config_parses_context_and_content_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            cfg = _write_config(repo, _base_config_text())

            loaded = load_repo_config(str(cfg))

            self.assertEqual(loaded.context.additional_files, [".shipnote/context.md", ".shipnote/notes.txt"])
            self.assertEqual(loaded.context.max_total_chars, 12000)
            self.assertEqual(loaded.content_policy.focus_topics, ["software engineering", "developer tooling"])
            self.assertEqual(loaded.content_policy.avoid_topics, ["politics", "sports"])
            self.assertIn("community discussions", loaded.content_policy.engagement_reminder)

    def test_load_repo_config_rejects_invalid_context_max_total_chars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            cfg = _write_config(repo, _base_config_text().replace("max_total_chars: 12000", "max_total_chars: 0"))

            with self.assertRaises(ShipnoteConfigError):
                load_repo_config(str(cfg))

    def test_load_repo_config_rejects_empty_focus_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            cfg = _write_config(
                repo,
                _base_config_text().replace(
                    'focus_topics:\n    - "software engineering"\n    - "developer tooling"',
                    "focus_topics: []",
                ),
            )

            with self.assertRaises(ShipnoteConfigError):
                load_repo_config(str(cfg))

    def test_load_repo_config_uses_global_defaults_and_repo_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])

            repo_cfg_text = _base_config_text().replace('queue_dir: ".shipnote/queue"\n', "")
            repo_cfg_text = repo_cfg_text.replace("poll_interval_seconds: 60", "poll_interval_seconds: 45")
            cfg = _write_config(repo, repo_cfg_text)

            global_defaults = root / "defaults.yaml"
            global_defaults.write_text(
                "\n".join(
                    [
                        'queue_dir: ".shipnote/global-drafts"',
                        "poll_interval_seconds: 120",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("shipnote.config_loader.default_global_defaults_path", return_value=global_defaults):
                loaded = load_repo_config(str(cfg))

            self.assertEqual(loaded.poll_interval_seconds, 45)
            self.assertEqual(loaded.queue_dir, (repo / ".shipnote/global-drafts").resolve())

    def test_load_repo_config_uses_builtin_queue_dir_when_missing_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])

            repo_cfg_text = _base_config_text().replace('queue_dir: ".shipnote/queue"\n', "")
            cfg = _write_config(repo, repo_cfg_text)
            missing_defaults_path = root / "missing-defaults.yaml"
            self.assertFalse(missing_defaults_path.exists())

            with patch("shipnote.config_loader.default_global_defaults_path", return_value=missing_defaults_path):
                loaded = load_repo_config(str(cfg))

            self.assertEqual(loaded.queue_dir, (repo / ".shipnote/drafts").resolve())

    def test_default_global_defaults_path_points_to_home_dot_shipnote(self) -> None:
        path = default_global_defaults_path()
        self.assertEqual(path.name, "defaults.yaml")
        self.assertEqual(path.parent.name, ".shipnote")


def _write_secrets(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


class SecretsAliasTests(unittest.TestCase):
    def test_shipnote_model_env_maps_to_axis_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(secrets_path, ["OPENAI_API_KEY=file-key"])
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(os.environ, {"SHIPNOTE_MODEL": "model-from-shipnote"}, clear=True):
                    load_secrets(required=True)
                    self.assertEqual(os.getenv(AXIS_MODEL_KEY), "model-from-shipnote")

    def test_axis_model_env_takes_precedence_over_shipnote_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(secrets_path, ["OPENAI_API_KEY=file-key"])
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(
                    os.environ,
                    {AXIS_MODEL_KEY: "axis-model", "SHIPNOTE_MODEL": "shipnote-model"},
                    clear=True,
                ):
                    load_secrets(required=True)
                    self.assertEqual(os.getenv(AXIS_MODEL_KEY), "axis-model")

    def test_shipnote_api_key_defaults_to_openai(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(secrets_path, [])
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(os.environ, {"SHIPNOTE_API_KEY": "shipnote-key"}, clear=True):
                    load_secrets(required=True)
                    self.assertEqual(os.getenv("OPENAI_API_KEY"), "shipnote-key")

    def test_shipnote_api_key_anthropic_provider_maps_to_anthropic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(secrets_path, [])
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(
                    os.environ,
                    {"SHIPNOTE_API_KEY": "shipnote-key", "SHIPNOTE_PROVIDER": "anthropic"},
                    clear=True,
                ):
                    load_secrets(required=True)
                    self.assertEqual(os.getenv("ANTHROPIC_API_KEY"), "shipnote-key")
                    self.assertIsNone(os.getenv("OPENAI_API_KEY"))

    def test_explicit_provider_key_precedes_shipnote_api_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(secrets_path, [])
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(
                    os.environ,
                    {"OPENAI_API_KEY": "explicit-key", "SHIPNOTE_API_KEY": "shipnote-key"},
                    clear=True,
                ):
                    load_secrets(required=True)
                    self.assertEqual(os.getenv("OPENAI_API_KEY"), "explicit-key")

    def test_process_shipnote_api_precedes_file_provider_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(secrets_path, ["OPENAI_API_KEY=file-key"])
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(os.environ, {"SHIPNOTE_API_KEY": "env-shipnote-key"}, clear=True):
                    load_secrets(required=True)
                    self.assertEqual(os.getenv("OPENAI_API_KEY"), "env-shipnote-key")

    def test_shipnote_aliases_from_secrets_file_are_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(
                secrets_path,
                [
                    "SHIPNOTE_API_KEY=file-shipnote-key",
                    "SHIPNOTE_PROVIDER=anthropic",
                    "SHIPNOTE_MODEL=file-shipnote-model",
                ],
            )
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(os.environ, {}, clear=True):
                    load_secrets(required=True)
                    self.assertEqual(os.getenv("ANTHROPIC_API_KEY"), "file-shipnote-key")
                    self.assertEqual(os.getenv(AXIS_MODEL_KEY), "file-shipnote-model")

    def test_invalid_shipnote_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.env"
            _write_secrets(secrets_path, [])
            with patch("shipnote.config_loader.default_secrets_path", return_value=secrets_path):
                with patch.dict(
                    os.environ,
                    {"SHIPNOTE_API_KEY": "shipnote-key", "SHIPNOTE_PROVIDER": "invalid"},
                    clear=True,
                ):
                    with self.assertRaises(ShipnoteSecretsError):
                        load_secrets(required=True)


if __name__ == "__main__":
    unittest.main()
