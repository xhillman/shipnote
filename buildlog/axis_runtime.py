"""axis-core runtime configuration helpers."""

from __future__ import annotations

import logging


def quiet_axis_logs() -> None:
    """Reduce noisy axis-core logger output in CLI daemon mode."""
    for name in ("axis_core", "axis_core.agent", "axis_core.engine", "axis_core.engine.lifecycle"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

