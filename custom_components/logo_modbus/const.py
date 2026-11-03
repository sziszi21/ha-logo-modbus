"""Constants for the Siemens LOGO! Modbus TCP integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "logo_modbus"

CONF_OUTPUTS: Final = "outputs"
CONF_INPUTS: Final = "inputs"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_PORT: Final = 502
DEFAULT_OUTPUTS: Final = 8
DEFAULT_INPUTS: Final = 8
DEFAULT_SCAN_INTERVAL: Final = 2  # seconds

MAX_OUTPUTS: Final = 20  # Q1..Q20
MAX_INPUTS: Final = 24  # I1..I24
MIN_SCAN_INTERVAL: Final = 1
MAX_SCAN_INTERVAL: Final = 60

# Modbus wire addresses (0-based). Siemens documents them 1-based (+1).
ADDR_INPUTS: Final = 0  # I1 -> discrete input 0 (documented 1)
ADDR_OUTPUTS: Final = 8192  # Q1 -> coil 8192 (documented 8193)
ADDR_FLAGS: Final = 8256  # M1 -> coil 8256 (documented 8257)

UNIT_ID: Final = 1  # The LOGO! ignores the unit id.
REQUEST_TIMEOUT: Final = 5.0  # seconds

MANUFACTURER: Final = "Siemens"
MODEL: Final = "LOGO! 8 (Modbus TCP)"
