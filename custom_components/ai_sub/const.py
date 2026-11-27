"""Constants for the AI Sub integration.

Everything that is *not* vendor specific lives here.  Plan tables, endpoints and
payload shapes belong to the provider modules under ``providers/``.
"""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "ai_sub"
NAME = "AI Sub"

CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_CURRENCY = "USD"

DEFAULT_SCAN_INTERVAL = 600
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
