"""Load settings from config.toml, .env, environment variables, and CLI overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    org_id: str
    api_key: str
    collections: tuple[str, ...]
    rows_per_page: int
    min_request_interval: float
    data_dir: Path
    base_url: str
    validation_dir: Path
    validator_base_url: str
    registry_base_url: str


def load_settings(
    *,
    org_id: str | None = None,
    collections: list[str] | None = None,
    data_dir: str | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    env_path: Path | None = DEFAULT_ENV_PATH,
    require_api_key: bool = True,
) -> Settings:
    """Resolve settings with precedence: explicit args > env vars > config.toml.

    `env_path` (default `.env` in the project root, if present) is loaded into
    the environment first, without overriding any variable already set in the
    real environment. Pass `env_path=None` to skip it (tests).
    """
    if env_path is not None:
        load_dotenv(env_path, override=False)

    file_config: dict = {}
    if config_path.exists():
        with config_path.open("rb") as f:
            file_config = tomllib.load(f)

    resolved_org_id = org_id or os.environ.get("IATI_ORG_ID") or file_config.get("org_id") or ""
    if not resolved_org_id:
        raise ConfigError(
            "No organisation ID configured. Pass --org-id, set IATI_ORG_ID, "
            "or set org_id in config.toml."
        )

    api_key = os.environ.get("IATI_API_KEY") or ""
    if not api_key and require_api_key:
        raise ConfigError(
            "No API key configured. Set IATI_API_KEY in your environment or in a .env file "
            "(see .env.example). Get a key at https://developer.iatistandard.org/."
        )

    resolved_collections = tuple(collections or file_config.get("collections") or [])
    if not resolved_collections:
        raise ConfigError(
            "No collections configured. Set collections in config.toml or pass --collections."
        )

    resolved_data_dir = Path(data_dir or file_config.get("data_dir") or "data/raw")
    if not resolved_data_dir.is_absolute():
        resolved_data_dir = PROJECT_ROOT / resolved_data_dir

    validation_dir = Path(file_config.get("validation_dir") or "data/validation")
    if not validation_dir.is_absolute():
        validation_dir = PROJECT_ROOT / validation_dir

    return Settings(
        org_id=resolved_org_id,
        api_key=api_key,
        collections=resolved_collections,
        rows_per_page=int(file_config.get("rows_per_page", 500)),
        min_request_interval=float(file_config.get("min_request_interval", 1.0)),
        data_dir=resolved_data_dir,
        base_url=str(file_config.get("base_url", "https://api.iatistandard.org/datastore")),
        validation_dir=validation_dir,
        validator_base_url=str(
            file_config.get("validator_base_url", "https://api.iatistandard.org/validator")
        ),
        registry_base_url=str(
            file_config.get("registry_base_url", "https://iatiregistry.org/api/3/action")
        ),
    )
