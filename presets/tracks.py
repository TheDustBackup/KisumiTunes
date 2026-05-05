import json
import random
from pathlib import Path

_PRESETS_FILE = Path(__file__).parent.parent / 'presets.json'


def _load() -> dict:
    with open(_PRESETS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _pick(value: str | list) -> str | None:
    if isinstance(value, list):
        options = [v for v in value if v]
        return random.choice(options) if options else None
    return value if value else None


def get_preset(channel_name: str) -> str:
    presets = _load()
    lower = channel_name.lower()
    # Sort by length descending so multi-word keywords ("hollow purple") match before single words
    for keyword in sorted(presets, key=len, reverse=True):
        if keyword.startswith('_'):
            continue
        if keyword in lower:
            return _pick(presets[keyword])
    return _pick(presets.get('_default', ''))


def describe_preset(channel_name: str) -> str:
    presets = _load()
    lower = channel_name.lower()
    for keyword in sorted(presets, key=len, reverse=True):
        if keyword.startswith('_'):
            continue
        if keyword in lower:
            return keyword
    return 'default ambient'


def get_by_name(name: str) -> str | None:
    """Look up a preset directly by exact key name (used by mood commands like --battle)."""
    presets = _load()
    value = presets.get(name)
    return _pick(value) if value else None


def get_mood(name: str) -> str | None:
    """Return the URL for a mood command (battle, rest, etc.) or None if not defined."""
    presets = _load()
    moods: dict = presets.get('_moods', {})
    value = moods.get(name)
    return _pick(value) if value else None


def match_oneshot(message: str) -> str | None:
    """Return a URL if the message matches a one-shot keyword, otherwise None."""
    presets = _load()
    oneshots: dict = presets.get('_oneshots', {})
    lower = message.lower()
    for keyword in sorted(oneshots, key=len, reverse=True):
        if keyword.startswith('_'):
            continue
        if keyword in lower:
            return _pick(oneshots[keyword])
    return None


def match_trigger(message: str) -> str | None:
    """Return a URL if the message contains a trigger word, otherwise None."""
    presets = _load()
    triggers: dict = presets.get('_triggers', {})
    lower = message.lower()
    # Longest keyword first so "hollow purple" beats "hollow"
    for keyword in sorted(triggers, key=len, reverse=True):
        if keyword.startswith('_'):
            continue
        if keyword in lower:
            return _pick(triggers[keyword])
    return None
