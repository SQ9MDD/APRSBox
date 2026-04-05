from __future__ import annotations

from dataclasses import dataclass


WX_SOURCE_TYPES = ("home_assistant", "domoticz")
WX_AUTH_TYPES = ("none", "bearer", "basic")
WX_SELECTOR_KINDS = ("state", "attribute", "field", "key")
WX_RUNTIME_STATUSES = ("LIVE", "CACHED", "STALE", "MISSING", "ERROR")


@dataclass(frozen=True, slots=True)
class WxParameterDefinition:
    name: str
    label: str
    aprs_field: str
    required: bool
    canonical_unit: str
    description: str


WX_PARAMETER_DEFINITIONS: tuple[WxParameterDefinition, ...] = (
    WxParameterDefinition(
        name="wind_direction_deg",
        label="Wind direction",
        aprs_field="ddd",
        required=True,
        canonical_unit="deg",
        description="APRS complete WX format requires wind direction in degrees.",
    ),
    WxParameterDefinition(
        name="wind_speed_mph",
        label="Wind speed",
        aprs_field="sss",
        required=True,
        canonical_unit="mph",
        description="APRS complete WX format requires sustained 1-minute wind speed in mph.",
    ),
    WxParameterDefinition(
        name="temperature_f",
        label="Temperature",
        aprs_field="t",
        required=True,
        canonical_unit="F",
        description="APRS complete WX format requires temperature in degrees Fahrenheit.",
    ),
    WxParameterDefinition(
        name="wind_gust_mph",
        label="Wind gust",
        aprs_field="g",
        required=False,
        canonical_unit="mph",
        description="Peak wind gust in mph during the recent gust window.",
    ),
    WxParameterDefinition(
        name="rain_last_hour_in",
        label="Rain last hour",
        aprs_field="r",
        required=False,
        canonical_unit="in",
        description="Rainfall during the last 60 minutes in inches.",
    ),
    WxParameterDefinition(
        name="rain_last_24h_in",
        label="Rain last 24 hours",
        aprs_field="p",
        required=False,
        canonical_unit="in",
        description="Rolling 24-hour rainfall in inches.",
    ),
    WxParameterDefinition(
        name="rain_since_midnight_in",
        label="Rain since midnight",
        aprs_field="P",
        required=False,
        canonical_unit="in",
        description="Rainfall since local midnight in inches.",
    ),
    WxParameterDefinition(
        name="humidity_pct",
        label="Humidity",
        aprs_field="h",
        required=False,
        canonical_unit="percent",
        description="Relative humidity in percent.",
    ),
    WxParameterDefinition(
        name="pressure_hpa",
        label="Barometric pressure",
        aprs_field="b",
        required=False,
        canonical_unit="hPa",
        description="Barometric pressure in hPa / mb.",
    ),
    WxParameterDefinition(
        name="snow_last_24h_in",
        label="Snow last 24 hours",
        aprs_field="s",
        required=False,
        canonical_unit="in",
        description="Snowfall during the last 24 hours in inches.",
    ),
    WxParameterDefinition(
        name="luminosity_w_m2",
        label="Luminosity",
        aprs_field="L/l",
        required=False,
        canonical_unit="W/m2",
        description="Luminosity in watts per square meter.",
    ),
    WxParameterDefinition(
        name="raw_rain_counter",
        label="Raw rain counter",
        aprs_field="#",
        required=False,
        canonical_unit="count",
        description="Raw rain counter value for stations that expose only bucket counts.",
    ),
    WxParameterDefinition(
        name="water_height_ft",
        label="Water height (feet)",
        aprs_field="F",
        required=False,
        canonical_unit="ft",
        description="Water or flood height in feet.",
    ),
    WxParameterDefinition(
        name="water_height_m",
        label="Water height (meters)",
        aprs_field="f",
        required=False,
        canonical_unit="m",
        description="Water or flood height in meters.",
    ),
    WxParameterDefinition(
        name="battery_volts",
        label="Battery voltage",
        aprs_field="V",
        required=False,
        canonical_unit="V",
        description="Battery voltage in volts.",
    ),
    WxParameterDefinition(
        name="radiation_nsv_h",
        label="Radiation",
        aprs_field="X",
        required=False,
        canonical_unit="nSv/h",
        description="Radiation level in nanosieverts per hour.",
    ),
)


WX_PARAMETER_BY_NAME = {item.name: item for item in WX_PARAMETER_DEFINITIONS}


def get_wx_parameter_definition(name: str) -> WxParameterDefinition:
    return WX_PARAMETER_BY_NAME[name]
