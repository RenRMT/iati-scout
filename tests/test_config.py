from pathlib import Path

import pytest

from iati_scout.config import ConfigError, load_settings


def _write_config(tmp_path: Path, extra: str = "") -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'org_id = "FILE-ORG"\n'
        'collections = ["activity"]\n'
        "rows_per_page = 250\n"
        "min_request_interval = 0.5\n"
        'data_dir = "data/raw"\n'
        'base_url = "https://example.test/datastore"\n' + extra,
        encoding="utf-8",
    )
    return config_path


def test_load_settings_from_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("IATI_API_KEY", "secret")
    monkeypatch.delenv("IATI_ORG_ID", raising=False)
    config_path = _write_config(tmp_path)

    settings = load_settings(config_path=config_path)

    assert settings.org_id == "FILE-ORG"
    assert settings.api_key == "secret"
    assert settings.collections == ("activity",)
    assert settings.rows_per_page == 250
    assert settings.min_request_interval == 0.5
    assert settings.base_url == "https://example.test/datastore"


def test_explicit_org_id_overrides_env_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("IATI_API_KEY", "secret")
    monkeypatch.setenv("IATI_ORG_ID", "ENV-ORG")
    config_path = _write_config(tmp_path)

    settings = load_settings(org_id="CLI-ORG", config_path=config_path)

    assert settings.org_id == "CLI-ORG"


def test_env_org_id_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("IATI_API_KEY", "secret")
    monkeypatch.setenv("IATI_ORG_ID", "ENV-ORG")
    config_path = _write_config(tmp_path)

    settings = load_settings(config_path=config_path)

    assert settings.org_id == "ENV-ORG"


def test_missing_org_id_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("IATI_API_KEY", "secret")
    monkeypatch.delenv("IATI_ORG_ID", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text('collections = ["activity"]\n', encoding="utf-8")

    with pytest.raises(ConfigError):
        load_settings(config_path=config_path)


def test_missing_api_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("IATI_API_KEY", raising=False)
    config_path = _write_config(tmp_path)

    with pytest.raises(ConfigError):
        load_settings(config_path=config_path)


def test_missing_collections_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("IATI_API_KEY", "secret")
    config_path = tmp_path / "config.toml"
    config_path.write_text('org_id = "FILE-ORG"\n', encoding="utf-8")

    with pytest.raises(ConfigError):
        load_settings(config_path=config_path)
