"""Keep the UI strings honest: en.json mirrors strings.json and covers entities."""

from __future__ import annotations

import json
import re
from pathlib import Path

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "ai_sub"
STRINGS = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
EN = json.loads((COMPONENT / "translations" / "en.json").read_text(encoding="utf-8"))


def test_english_translation_mirrors_strings() -> None:
    assert EN == STRINGS


def test_every_entity_translation_key_is_declared() -> None:
    for platform in ("sensor", "binary_sensor"):
        source = (COMPONENT / f"{platform}.py").read_text(encoding="utf-8")
        keys = set(re.findall(r'_attr_translation_key = "([^"]+)"', source))
        declared = set(STRINGS["entity"][platform])
        assert keys == declared, platform


def test_every_provider_credential_has_a_label() -> None:
    from custom_components.ai_sub.providers import PROVIDERS

    for provider in PROVIDERS.values():
        for field in provider.config_fields:
            for step in ("credentials", "reauth_confirm"):
                labels = STRINGS["config"]["step"][step]["data"]
                assert field.translation_key in labels, (provider.name, field.key, step)
