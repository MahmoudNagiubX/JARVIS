"""Editable owner personalization contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PersonalizationProfile:
    owner_id: str
    values: Mapping[str, object] = field(default_factory=dict)
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PersonalizationUpdate:
    key: str
    value: object
    source: str = "user"
