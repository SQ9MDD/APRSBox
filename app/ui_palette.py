from __future__ import annotations

DEFAULT_UI_PALETTE = "green-core"

UI_PALETTE_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "green-core", "label": "Green Core (default)"},
    {"value": "red-tactic", "label": "Red Tactic"},
    {"value": "forest-pine", "label": "Forest Pine"},
    {"value": "nordic-blue", "label": "Nordic Blue"},
    {"value": "slate-cyan", "label": "Slate Cyan"},
    {"value": "amber-graphite", "label": "Amber Graphite"},
    {"value": "crimson-ops", "label": "Crimson Ops"},
    {"value": "violet-signal", "label": "Violet Signal"},
    {"value": "monochrome-neutral", "label": "Monochrome Neutral"},
    {"value": "copper-radar", "label": "Copper Radar"},
    {"value": "orange-workshop", "label": "Orange Workshop"},
    {"value": "pastel-mint", "label": "Pastel Mint"},
    {"value": "pastel-lavender", "label": "Pastel Lavender"},
    {"value": "pastel-peach", "label": "Pastel Peach"},
    {"value": "pastel-rose", "label": "Pastel Rose"},
    {"value": "pastel-sky", "label": "Pastel Sky"},
    {"value": "pastel-lemon", "label": "Pastel Lemon"},
    {"value": "pastel-sage", "label": "Pastel Sage"},
    {"value": "dusty-pink", "label": "Dusty Pink"},
    {"value": "powder-blue", "label": "Powder Blue"},
    {"value": "lilac-dream", "label": "Lilac Dream"},
    {"value": "coral-bay", "label": "Coral Bay"},
    {"value": "turquoise-wave", "label": "Turquoise Wave"},
    {"value": "petrol-night", "label": "Petrol Night"},
    {"value": "royal-blue", "label": "Royal Blue"},
    {"value": "deep-indigo", "label": "Deep Indigo"},
    {"value": "deep-purple", "label": "Deep Purple"},
    {"value": "electric-magenta", "label": "Electric Magenta"},
    {"value": "olive-field", "label": "Olive Field"},
    {"value": "desert-sand", "label": "Desert Sand"},
    {"value": "earth-brown", "label": "Earth Brown"},
    {"value": "teal-horizon", "label": "Teal Horizon"},
    {"value": "emerald-city", "label": "Emerald City"},
    {"value": "ice-blue", "label": "Ice Blue"},
    {"value": "retro-terminal", "label": "Retro Terminal"},
    {"value": "synthwave", "label": "Synthwave"},
    {"value": "warm-gray", "label": "Warm Gray"},
    {"value": "cold-gray", "label": "Cold Gray"},
    {"value": "midnight-navy", "label": "Midnight Navy"},
    {"value": "burgundy-wine", "label": "Burgundy Wine"},
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
