"""Security and restart-boundary regressions for the three-model desktop brain."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from jarvis.__main__ import _cloud_key_store_action, _secure_provider_keys_for_runtime
from jarvis.config import JarvisConfig
from jarvis.desktop.config import DesktopProductConfig
from jarvis.desktop.lifecycle import JarvisDesktopLifecycle
from jarvis.desktop.secret_store import (
    CLOUD_PROVIDER_SECRET_KEYS,
    MemorySecretStore,
    cloud_provider_secret_states,
    read_cloud_provider_keys,
)
from jarvis.models.gateway import ModelGateway


def _hybrid_config(database_path: Path | str = ":memory:") -> JarvisConfig:
    return JarvisConfig(
        environment="test",
        database_path=str(database_path),
        model_provider="hybrid",
        groq_enabled=True,
        gemini_enabled=True,
    )


def test_cloud_secret_identifiers_round_trip_replace_and_delete() -> None:
    store = MemorySecretStore()

    assert CLOUD_PROVIDER_SECRET_KEYS == {
        "groq": "jarvis-groq-api-key",
        "gemini": "jarvis-gemini-api-key",
    }
    assert cloud_provider_secret_states(store) == {"groq": "missing_key", "gemini": "missing_key"}

    store.set(CLOUD_PROVIDER_SECRET_KEYS["groq"], "groq-first")
    store.set(CLOUD_PROVIDER_SECRET_KEYS["groq"], "groq-replaced")
    store.set(CLOUD_PROVIDER_SECRET_KEYS["gemini"], "gemini-value")
    assert read_cloud_provider_keys(store) == {"groq": "groq-replaced", "gemini": "gemini-value"}
    assert cloud_provider_secret_states(store) == {"groq": "configured", "gemini": "configured"}

    store.delete(CLOUD_PROVIDER_SECRET_KEYS["groq"])
    assert read_cloud_provider_keys(store)["groq"] == ""
    assert cloud_provider_secret_states(store)["groq"] == "missing_key"


def test_hidden_key_command_writes_only_secure_store_and_never_outputs_value(capsys) -> None:
    store = MemorySecretStore()
    secret = "gsk_secret_must_not_escape"

    with patch("jarvis.desktop.secret_store.platform_secret_store", return_value=store), \
         patch("getpass.getpass", return_value=secret):
        assert _cloud_key_store_action("groq") == 0

    output = capsys.readouterr().out
    assert secret not in output
    assert "configured" in output
    assert store.get(CLOUD_PROVIDER_SECRET_KEYS["groq"]) == secret
    assert os.environ.get("GROQ_API_KEY") != secret

    with patch("jarvis.desktop.secret_store.platform_secret_store", return_value=store):
        assert _cloud_key_store_action("groq", delete=True) == 0
    assert store.get(CLOUD_PROVIDER_SECRET_KEYS["groq"]) is None
    assert secret not in capsys.readouterr().out


def test_secure_mapping_is_injected_into_providers_and_blocks_environment_fallback(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "wrong-environment-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "wrong-environment-gemini")
    gateway = ModelGateway(
        _hybrid_config(),
        providers={"local": object()},
        provider_api_keys={"groq": "secure-groq", "gemini": "secure-gemini"},
    )

    assert gateway.providers["groq"]._api_key == "secure-groq"
    assert gateway.providers["gemini"]._api_key == "secure-gemini"
    assert "secure-groq" not in json.dumps(gateway.architecture_snapshot())
    assert "secure-gemini" not in json.dumps(gateway.architecture_snapshot())

    missing = ModelGateway(
        _hybrid_config(),
        providers={"local": object()},
        provider_api_keys={"groq": "", "gemini": ""},
    )
    assert missing.providers["groq"]._api_key == ""
    assert missing.providers["gemini"]._api_key == ""
    assert missing.architecture_snapshot()["groq"]["state"] == "missing_key"
    assert missing.architecture_snapshot()["gemini"]["state"] == "missing_key"


def test_normal_cli_runtime_prefers_store_but_empty_store_preserves_probe_compatibility() -> None:
    store = MemorySecretStore()
    with patch("jarvis.desktop.secret_store.platform_secret_store", return_value=store):
        assert _secure_provider_keys_for_runtime() is None
        store.set(CLOUD_PROVIDER_SECRET_KEYS["groq"], "secure-groq")
        assert _secure_provider_keys_for_runtime() == {"groq": "secure-groq", "gemini": ""}


def test_desktop_runtime_reads_secure_keys_without_putting_them_in_config_or_settings(tmp_path: Path) -> None:
    store = MemorySecretStore()
    store.set(CLOUD_PROVIDER_SECRET_KEYS["groq"], "secure-groq")
    store.set(CLOUD_PROVIDER_SECRET_KEYS["gemini"], "secure-gemini")
    settings = DesktopProductConfig()
    settings_path = tmp_path / "settings.json"
    settings.save(settings_path)

    lifecycle = JarvisDesktopLifecycle(
        config_path=settings_path,
        secret_store=store,
        base_config_factory=_hybrid_config,
    )
    runtime = lifecycle._new_runtime(settings)
    try:
        assert runtime.config.model_provider == "hybrid"
        assert runtime.models.providers["groq"]._api_key == "secure-groq"
        assert runtime.models.providers["gemini"]._api_key == "secure-gemini"
        assert "secure-groq" not in repr(runtime.config)
        assert "secure-gemini" not in repr(runtime.config)
        assert "secure-groq" not in settings_path.read_text(encoding="utf-8")
        assert "secure-gemini" not in settings_path.read_text(encoding="utf-8")
        database_path = Path(runtime.config.database_path)
        if database_path.exists():
            database_bytes = database_path.read_bytes()
            assert b"secure-groq" not in database_bytes
            assert b"secure-gemini" not in database_bytes
    finally:
        runtime.database.close()


def test_desktop_runtime_never_reads_cloud_keys_from_process_environment(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "environment-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "environment-gemini")
    lifecycle = JarvisDesktopLifecycle(
        secret_store=MemorySecretStore(),
        base_config_factory=_hybrid_config,
    )
    runtime = lifecycle._new_runtime(DesktopProductConfig())
    try:
        assert runtime.models.providers["groq"]._api_key == ""
        assert runtime.models.providers["gemini"]._api_key == ""
    finally:
        runtime.database.close()


def test_desktop_settings_persist_only_non_secret_three_model_enablement(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = DesktopProductConfig(groq_enabled=True, gemini_enabled=True)
    settings.save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["model_provider"] == "hybrid"
    assert payload["groq_model"] == "openai/gpt-oss-120b"
    assert payload["gemini_model"] == "gemini-3.5-flash"
    assert "api_key" not in json.dumps(payload).casefold()
    assert "secret" not in json.dumps(payload).casefold()
