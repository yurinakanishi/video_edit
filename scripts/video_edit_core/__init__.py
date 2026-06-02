from __future__ import annotations

from pathlib import Path


CORE = Path(__file__).resolve().parents[2] / "video_edit_core"
__path__ = [str(CORE)]

