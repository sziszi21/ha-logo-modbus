"""Config and options flow tests."""

from __future__ import annotations

import socket

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries  # noqa: E402
from homeassistant.const import CONF_HOST, CONF_PORT  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.logo_modbus.const import (  # noqa: E402
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

from .fake_logo import FakeLogo  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_user_flow_creates_entry(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: " 127.0.0.1 ",
            CONF_PORT: float(fake_logo.port),  # number selectors send floats
            CONF_OUTPUTS: 8.0,
            CONF_INPUTS: 6.0,
            CONF_SCAN_INTERVAL: 2.0,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LOGO! (127.0.0.1)"
    assert result["data"] == {
        CONF_HOST: "127.0.0.1",
        CONF_PORT: fake_logo.port,
        CONF_OUTPUTS: 8,
        CONF_INPUTS: 6,
        CONF_SCAN_INTERVAL: 2,
    }
    assert all(isinstance(v, int) for k, v in result["data"].items() if k != CONF_HOST)
    entry = result["result"]
    assert entry.unique_id == f"127.0.0.1:{fake_logo.port}"
    # Validation read I1 = discrete input 0
    assert (0x02, 0, 1) in fake_logo.requests

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "127.0.0.1",
            CONF_PORT: _free_port(),
            CONF_OUTPUTS: 8,
            CONF_INPUTS: 8,
            CONF_SCAN_INTERVAL: 2,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="127.0.0.1:502",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 502},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 502,
            CONF_OUTPUTS: 8,
            CONF_INPUTS: 8,
            CONF_SCAN_INTERVAL: 2,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"127.0.0.1:{fake_logo.port}",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake_logo.port,
            CONF_OUTPUTS: 8,
            CONF_INPUTS: 8,
            CONF_SCAN_INTERVAL: 2,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_OUTPUTS: 2.0, CONF_INPUTS: 0.0, CONF_SCAN_INTERVAL: 5.0},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_OUTPUTS: 2, CONF_INPUTS: 0, CONF_SCAN_INTERVAL: 5}

    # Entry reloaded with the new counts.
    assert hass.states.get("switch.logo_127_0_0_1_q2") is not None
    assert hass.states.get("switch.logo_127_0_0_1_q3") is None
    assert hass.states.get("binary_sensor.logo_127_0_0_1_i1") is None
    assert entry.runtime_data.output_count == 2

    assert await hass.config_entries.async_unload(entry.entry_id)
