"""Shared fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import importlib.util

import pytest

from .fake_logo import FakeLogo

HAS_HA = importlib.util.find_spec("pytest_homeassistant_custom_component") is not None

if HAS_HA:
    # The plugin itself is auto-loaded through its pytest11 entry point.

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Load custom_components/ in every Home Assistant test."""
        yield


@pytest.fixture
async def fake_logo() -> AsyncGenerator[FakeLogo]:
    """A running fake LOGO! on 127.0.0.1."""
    fake = FakeLogo()
    await fake.start()
    yield fake
    await fake.stop()
    await asyncio.sleep(0)
