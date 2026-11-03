"""Setup, entity and coordinator tests against the fake LOGO!."""

from __future__ import annotations

from datetime import timedelta
import socket

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.switch import (  # noqa: E402
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.const import (  # noqa: E402
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_PORT,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.exceptions import HomeAssistantError  # noqa: E402
from homeassistant.helpers import device_registry as dr, entity_registry as er  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.logo_modbus.const import (  # noqa: E402
    CONF_INPUTS,
    CONF_OUTPUTS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

from .fake_logo import FakeLogo  # noqa: E402

PREFIX = "logo_127_0_0_1"


async def _setup(hass: HomeAssistant, port: int, outputs: int = 8, inputs: int = 8):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LOGO! (127.0.0.1)",
        unique_id=f"127.0.0.1:{port}",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: port,
            CONF_OUTPUTS: outputs,
            CONF_INPUTS: inputs,
            CONF_SCAN_INTERVAL: 2,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _switch(hass: HomeAssistant, service: str, n: int) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN,
        service,
        {ATTR_ENTITY_ID: f"switch.{PREFIX}_q{n}"},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_entities_and_device(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    fake_logo.inputs[1] = True  # I2
    fake_logo.physical[4] = True  # Q5 on by program logic
    entry = await _setup(hass, fake_logo.port, outputs=8, inputs=6)
    assert entry.state is ConfigEntryState.LOADED

    ent_reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    assert len([e for e in entities if e.domain == "switch"]) == 8
    assert len([e for e in entities if e.domain == "binary_sensor"]) == 6
    assert ent_reg.async_get(f"switch.{PREFIX}_q1").unique_id == f"{entry.entry_id}_q1"
    assert ent_reg.async_get(f"binary_sensor.{PREFIX}_i1").unique_id == f"{entry.entry_id}_i1"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    assert devices[0].name == "LOGO! (127.0.0.1)"
    assert devices[0].manufacturer == "Siemens"
    assert {e.device_id for e in entities} == {devices[0].id}

    assert hass.states.get(f"binary_sensor.{PREFIX}_i1").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_i2").state == STATE_ON
    assert hass.states.get(f"switch.{PREFIX}_q1").state == STATE_OFF
    assert hass.states.get(f"switch.{PREFIX}_q5").state == STATE_ON
    assert hass.states.get(f"switch.{PREFIX}_q1").attributes["control_flag"] == "M1"

    # Poll reads Q from coil 8192 and I from discrete input 0.
    assert (0x01, 8192, 8) in fake_logo.requests
    assert (0x02, 0, 6) in fake_logo.requests

    client = entry.runtime_data.client
    assert client.connected
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not client.connected


async def test_switch_writes_flag_and_shows_q(
    hass: HomeAssistant, fake_logo: FakeLogo
) -> None:
    entry = await _setup(hass, fake_logo.port)

    await _switch(hass, SERVICE_TURN_ON, 3)
    assert (0x05, 8258, 0xFF00) in fake_logo.requests  # M3
    assert fake_logo.flags[2] is True
    assert not any(r[0] == 0x05 and 8192 <= r[1] < 8212 for r in fake_logo.requests)
    assert hass.states.get(f"switch.{PREFIX}_q3").state == STATE_ON

    await _switch(hass, SERVICE_TURN_OFF, 3)
    assert (0x05, 8258, 0x0000) in fake_logo.requests
    assert hass.states.get(f"switch.{PREFIX}_q3").state == STATE_OFF

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_or_behaviour_bounces_back(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    fake_logo.physical[0] = True
    entry = await _setup(hass, fake_logo.port)

    await _switch(hass, SERVICE_TURN_OFF, 1)
    assert fake_logo.flags[0] is False
    assert hass.states.get(f"switch.{PREFIX}_q1").state == STATE_ON

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_input_change_follows_poll(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    entry = await _setup(hass, fake_logo.port)
    assert hass.states.get(f"binary_sensor.{PREFIX}_i8").state == STATE_OFF

    fake_logo.inputs[7] = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(f"binary_sensor.{PREFIX}_i8").state == STATE_ON

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unavailable_and_recovery(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    port = fake_logo.port
    entry = await _setup(hass, port)
    assert hass.states.get(f"switch.{PREFIX}_q1").state == STATE_OFF

    await fake_logo.stop()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(f"switch.{PREFIX}_q1").state == STATE_UNAVAILABLE
    assert hass.states.get(f"binary_sensor.{PREFIX}_i1").state == STATE_UNAVAILABLE

    await fake_logo.start(port)
    fake_logo.physical[0] = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(f"switch.{PREFIX}_q1").state == STATE_ON

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_write_failure_raises(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    entry = await _setup(hass, fake_logo.port)
    fake_logo.reject_writes = True

    with pytest.raises(HomeAssistantError) as exc:
        await _switch(hass, SERVICE_TURN_ON, 2)
    assert exc.value.translation_key == "write_failed"
    assert exc.value.translation_placeholders["flag"] == "M2"
    # Exception response does not break the connection; state still read.
    assert hass.states.get(f"switch.{PREFIX}_q2").state == STATE_OFF

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_retry_when_unreachable(hass: HomeAssistant) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    entry = await _setup(hass, port)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_zero_counts(hass: HomeAssistant, fake_logo: FakeLogo) -> None:
    entry = await _setup(hass, fake_logo.port, outputs=0, inputs=3)
    assert entry.state is ConfigEntryState.LOADED
    assert not any(r[0] == 0x01 for r in fake_logo.requests)
    assert hass.states.get(f"binary_sensor.{PREFIX}_i3") is not None
    assert hass.states.async_entity_ids(SWITCH_DOMAIN) == []
    assert await hass.config_entries.async_unload(entry.entry_id)
