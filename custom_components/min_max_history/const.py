"""Constants for Min/Max History."""

DOMAIN = "min_max_history"
PLATFORMS = ["sensor"]

CONF_SOURCE_SENSOR = "source_sensor"
CONF_TIME_WINDOW = "time_window"
CONF_TIME_UNIT = "time_unit"
CONF_MAX = "max"
CONF_MIN = "min"

DEFAULT_TIME_WINDOW = 24
DEFAULT_TIME_UNIT = "hour"

TIME_UNITS = ["minute", "hour", "day", "week", "month", "year"]

UNIT_SECONDS = {
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    # month/year use calendar arithmetic (dateutil.relativedelta); the
    # values below are only fallbacks.
    "month": 2592000,
    "year": 31536000,
}

UNIT_SHORT = {
    "minute": "m",
    "hour": "h",
    "day": "d",
    "week": "w",
    "month": "mo",
    "year": "y",
}
