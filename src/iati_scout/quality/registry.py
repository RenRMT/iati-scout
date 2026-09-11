"""Rule registry: `@rule(...)` decorator, rule configuration, and the run context."""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iati_scout.config import PROJECT_ROOT
from iati_scout.quality.findings import Issue, Severity
from iati_scout.quality.model import Activity, Dataset

DEFAULT_RULES_PATH = PROJECT_ROOT / "rules.toml"

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "stale_months": 12,
    "budget_max_days": 366,
    "budget_min_days": 28,
    "disbursed_tolerance": 0.01,
    "commitment_tolerance": 0.001,
    "budget_vs_commitment_ratio": 0.5,
    "value_date_max_days": 366,
    "min_transaction_value": 1.0,
    "title_min_length": 10,
    "description_min_length": 30,
    "percentage_tolerance": 0.5,
    "truncation_lengths": [255, 256, 500, 1000, 2000, 4000],
    "home_country": "NL",
    "home_bbox": [50.5, 3.2, 53.7, 7.3],
}


@dataclass
class Context:
    """Everything a rule may need besides the activity itself."""

    dataset: Dataset
    thresholds: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))

    @property
    def today(self):
        return self.dataset.today

    def t(self, name: str) -> Any:
        return self.thresholds[name]


RuleFn = Callable[[Activity, Context], Iterator[Issue]]


@dataclass(frozen=True)
class RuleSpec:
    code: str
    severity: Severity
    title: str
    func: RuleFn
    description: str = ""

    @property
    def section(self) -> str:
        # "E-A01" -> "A"
        return self.code.split("-", 1)[1][0]


_REGISTRY: dict[str, RuleSpec] = {}


def rule(code: str, severity: Severity, title: str, description: str = ""):
    """Register a rule function `(activity, ctx) -> Iterator[Issue]`."""

    def decorator(func: RuleFn) -> RuleFn:
        if code in _REGISTRY:
            raise ValueError(f"Duplicate rule code {code}")
        _REGISTRY[code] = RuleSpec(
            code=code, severity=severity, title=title, func=func, description=description
        )
        return func

    return decorator


def all_rules() -> list[RuleSpec]:
    # Import rule modules for their registration side effect.
    from iati_scout.quality import rules  # noqa: F401

    return sorted(_REGISTRY.values(), key=lambda r: r.code)


def get_rule(code: str) -> RuleSpec:
    all_rules()
    return _REGISTRY[code]


@dataclass
class RuleConfig:
    enabled: dict[str, bool] = field(default_factory=dict)
    systemic: dict[str, bool] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))

    def is_enabled(self, code: str) -> bool:
        return self.enabled.get(code, True)

    def is_systemic(self, code: str) -> bool:
        return self.systemic.get(code, False)


def load_rule_config(path: Path = DEFAULT_RULES_PATH) -> RuleConfig:
    config = RuleConfig()
    if not path.exists():
        return config
    with path.open("rb") as f:
        data = tomllib.load(f)
    config.thresholds.update(data.get("thresholds", {}))
    for code, settings in data.get("rules", {}).items():
        if "enabled" in settings:
            config.enabled[code] = bool(settings["enabled"])
        if "systemic" in settings:
            config.systemic[code] = bool(settings["systemic"])
    return config
