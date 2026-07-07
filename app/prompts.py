"""
Editable agent prompts.

Each agent keeps its DEFAULT prompt as a module constant and reads it through
`render(key, default, **vars)` — so if a live override exists it's used, otherwise the
default. Overrides persist to a small JSON file. A safe formatter leaves unknown
{placeholders} literal (and respects {{ }} JSON braces) so a bad edit can't crash a run.
"""
from __future__ import annotations

import json
import string
import threading
from pathlib import Path
from typing import Any

from . import config

_LOCK = threading.Lock()
_PATH = Path(config.DB_PATH).parent / "prompt_overrides.json"

# human-facing metadata for the UI (label + the {placeholders} an edit must keep)
REGISTRY = {
    "strategist": {"label": "Strategist — brand extraction", "vars": []},
    "copywriter": {"label": "Copywriter — ad angles", "vars": ["{doctrine}"]},
    "art_director": {"label": "Art Director — scene prompt", "vars": ["{region}"]},
    "critic": {"label": "Critic — scoring rubric", "vars": ["{tone}", "{rules}", "{palette}", "{hook}", "{headline}", "{subhead}", "{cta}"]},
}


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _load() -> dict[str, str]:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(key: str, default: str) -> str:
    return _load().get(key, default)


def render(key: str, default: str, **kw: Any) -> str:
    tpl = get(key, default)
    try:
        return string.Formatter().vformat(tpl, (), _SafeDict(**kw))
    except Exception:
        return default.format(**kw)  # fall back to the known-good default


def set_override(key: str, value: str) -> None:
    with _LOCK:
        d = _load()
        d[key] = value
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def reset(key: str) -> None:
    with _LOCK:
        d = _load()
        d.pop(key, None)
        _PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def is_overridden(key: str) -> bool:
    return key in _load()
