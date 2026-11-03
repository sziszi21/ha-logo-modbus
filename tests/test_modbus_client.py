"""Tests for the minimal Modbus TCP client (no Home Assistant needed)."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.logo_modbus.modbus_client import (
    LogoModbusClient,
    LogoModbusError,
    LogoModbusExceptionResponse,
)

from .fake_logo import FakeLogo


@pytest.fixture
async def logo():
    fake = FakeLogo()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
async def client(logo: FakeLogo):
    c = LogoModbusClient("127.0.0.1", logo.port, timeout=1.0)
    yield c
    await c.close()


async def test_read_inputs_and_outputs(logo: FakeLogo, client: LogoModbusClient) -> None:
    logo.inputs[0] = True
    logo.inputs[7] = True
    logo.inputs[8] = True  # crosses a byte boundary
    logo.physical[2] = True

    assert await client.read_discrete_inputs(0, 9) == [
        True, False, False, False, False, False, False, True, True
    ]
    assert await client.read_coils(8192, 4) == [False, False, True, False]
    assert logo.unit_ids == [1, 1]


async def test_write_flag_drives_output(logo: FakeLogo, client: LogoModbusClient) -> None:
    await client.write_coil(8256, True)  # M1
    assert logo.flags[0] is True
    assert (await client.read_coils(8192, 2)) == [True, False]  # Q1 on

    await client.write_coil(8256, False)
    assert (await client.read_coils(8192, 1)) == [False]
    assert (0x05, 8256, 0xFF00) in logo.requests
    assert (0x05, 8256, 0x0000) in logo.requests


async def test_or_behaviour(logo: FakeLogo, client: LogoModbusClient) -> None:
    logo.physical[0] = True
    await client.write_coil(8256, False)
    assert (await client.read_coils(8192, 1)) == [True]  # Q1 still on


async def test_exception_response_keeps_connection(
    logo: FakeLogo, client: LogoModbusClient
) -> None:
    with pytest.raises(LogoModbusExceptionResponse) as exc:
        await client.read_discrete_inputs(20, 10)  # beyond I24
    assert exc.value.code == 0x02
    assert client.connected
    assert await client.read_discrete_inputs(0, 1) == [False]


async def test_reconnect_after_drop(logo: FakeLogo, client: LogoModbusClient) -> None:
    assert await client.read_coils(8192, 1) == [False]
    logo.drop_clients()
    await asyncio.sleep(0.05)
    # First request may fail on the dead socket, the next one reconnects.
    try:
        await client.read_coils(8192, 1)
    except LogoModbusError:
        pass
    assert await client.read_coils(8192, 1) == [False]


async def test_reconnect_after_close(logo: FakeLogo, client: LogoModbusClient) -> None:
    await client.read_coils(8192, 1)
    await client.close()
    assert not client.connected
    assert await client.read_coils(8192, 1) == [False]


async def test_timeout(logo: FakeLogo) -> None:
    logo.silent = True
    c = LogoModbusClient("127.0.0.1", logo.port, timeout=0.2)
    with pytest.raises(LogoModbusError):
        await c.read_coils(8192, 1)
    assert not c.connected
    await c.close()


async def test_connection_refused(closed_port: int) -> None:
    c = LogoModbusClient("127.0.0.1", closed_port, timeout=1.0)
    with pytest.raises(LogoModbusError):
        await c.read_discrete_inputs(0, 1)


async def test_invalid_arguments(client: LogoModbusClient) -> None:
    with pytest.raises(ValueError):
        await client.read_coils(8192, 0)
    with pytest.raises(ValueError):
        await client.write_coil(70000, True)
