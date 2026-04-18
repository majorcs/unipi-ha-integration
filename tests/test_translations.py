"""Translation and metadata smoke tests."""

from __future__ import annotations

import json
from pathlib import Path


def test_manifest_has_required_metadata() -> None:
    """The integration manifest should stay HACS-compatible."""
    manifest = json.loads(Path("custom_components/unipi/manifest.json").read_text())

    assert manifest["domain"] == "unipi"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_push"
    assert manifest["version"]
    assert manifest["documentation"]
    assert manifest["issue_tracker"]
    assert manifest["codeowners"]


def test_translation_contains_config_keys() -> None:
    """The English translation file should contain the config flow labels."""
    translations = json.loads(Path("custom_components/unipi/translations/en.json").read_text())

    assert translations["config"]["step"]["user"]["data"] == {
        "host": "Host or IP address",
        "port": "Port",
    }
    assert translations["config"]["error"]["cannot_connect"]
