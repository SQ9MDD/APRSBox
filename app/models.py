from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ROLES = ("admin", "operator", "viewer")


@dataclass(slots=True)
class UserIdentity:
    id: int
    username: str
    role: str
    is_active: bool


@dataclass(slots=True)
class SectionDefinition:
    slug: str
    title: str
    description: str
    table_name: str
    fields: list[dict[str, Any]]
    readonly_message: str
    nav_key: str
    create_roles: tuple[str, ...] = ("admin", "operator")

