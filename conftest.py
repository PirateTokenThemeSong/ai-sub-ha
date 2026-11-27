"""Load the Home Assistant test harness for the AI Sub tests."""

from __future__ import annotations

import sys

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    yield


if sys.platform == "win32":
    # The Home Assistant harness blocks sockets to catch accidental network
    # calls, but asyncio's ProactorEventLoop builds its wakeup pipe with an
    # AF_INET socketpair, which the guard rejects.  Neutralise the guard on
    # Windows only: HTTP is still mocked through ``aioclient_mock``, so no test
    # reaches the network.
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: pytest_socket.enable_socket()
