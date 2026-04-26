from __future__ import annotations

DEFAULT_UI_PALETTE = "green-core"

UI_PALETTE_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "green-core", "label": "Green Core (default)"},
    {"value": "forest-pine", "label": "Forest Pine"},
    {"value": "nordic-blue", "label": "Nordic Blue"},
    {"value": "slate-cyan", "label": "Slate Cyan"},
    {"value": "amber-graphite", "label": "Amber Graphite"},
    {"value": "crimson-ops", "label": "Crimson Ops"},
    {"value": "violet-signal", "label": "Violet Signal"},
    {"value": "monochrome-neutral", "label": "Monochrome Neutral"},
    {"value": "copper-radar", "label": "Copper Radar"},
)

UI_PALETTE_VALUES = frozenset(option["value"] for option in UI_PALETTE_OPTIONS)


def normalize_ui_palette(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in UI_PALETTE_VALUES:
        return normalized
    return DEFAULT_UI_PALETTE


def is_supported_ui_palette(value: str | None) -> bool:
    return str(value or "").strip().lower() in UI_PALETTE_VALUES


def get_ui_palette_options() -> list[dict[str, str]]:
    return [dict(option) for option in UI_PALETTE_OPTIONS]


def get_ui_palette_label(value: str | None) -> str:
    normalized = normalize_ui_palette(value)
    for option in UI_PALETTE_OPTIONS:
        if option["value"] == normalized:
            return option["label"]
    return "Green Core (default)"
