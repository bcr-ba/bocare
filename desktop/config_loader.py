"""Loads the desktop client's configuration from desktop/config/ (settings, texts, colours, stylesheet)."""
import os
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Any, Dict, Tuple

import yaml
from pydantic import BaseModel, model_validator

CONFIG_DIR = Path(__file__).resolve().parent / "config"


class DesktopSettings(BaseModel):
    api_url: str
    connect_timeout_seconds: float
    request_timeout_seconds: float
    max_input_length: int
    counter_from_ratio: float
    high_urgency_level: int
    medium_urgency_level: int
    window_min_size: Tuple[int, int]
    window_default_size: Tuple[int, int]
    logo_height: int
    bubble_max_width: int
    bubble_width_ratio: float
    input_max_lines: int
    progress_refresh_ms: int


class Strings(BaseModel):
    fr: Dict[str, Any]
    en: Dict[str, Any]

    @model_validator(mode="after")
    def same_keys(self) -> "Strings":
        if set(self.fr) != set(self.en):
            raise ValueError(f"strings.yml: keys differ between fr and en: {sorted(set(self.fr) ^ set(self.en))}")
        return self


def _read(name: str) -> Any:
    with (CONFIG_DIR / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def settings() -> DesktopSettings:
    data = _read("settings.yml")
    data["api_url"] = os.getenv("BOCARE_API_URL", data["api_url"])
    return DesktopSettings.model_validate(data)


@lru_cache
def strings() -> Dict[str, Dict[str, Any]]:
    return Strings.model_validate(_read("strings.yml")).model_dump()


@lru_cache
def colors() -> Dict[str, str]:
    return _read("theme.yml")


@lru_cache
def stylesheet() -> str:
    template = (CONFIG_DIR / "style.qss").read_text(encoding="utf-8")
    return Template(template).substitute(colors())
