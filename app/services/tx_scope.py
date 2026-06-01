from __future__ import annotations

from typing import Any

TX_SCOPE_SINGLE = "single"
TX_SCOPE_ALL_ACTIVE = "all_active"
TX_SCOPE_VALUES = {TX_SCOPE_SINGLE, TX_SCOPE_ALL_ACTIVE}
ALL_ACTIVE_INTERFACE_OPTION_VALUE = "__ALL_ACTIVE__"
INTERNAL_TX_INTERFACE_OPTION_VALUE = "__INTERNAL_TX__"


def normalize_tx_scope(value: Any, *, default: str = TX_SCOPE_SINGLE) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in TX_SCOPE_VALUES:
        return normalized
    return default if default in TX_SCOPE_VALUES else TX_SCOPE_SINGLE
