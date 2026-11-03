"""Minimal asyncio Modbus TCP client for the Siemens LOGO! 8.

Only the function codes this integration needs are implemented:

* 0x01 Read Coils
* 0x02 Read Discrete Inputs
* 0x05 Write Single Coil

Kept dependency-free on purpose so it never clashes with the pymodbus
version pinned by Home Assistant core.
"""

from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

FC_READ_COILS = 0x01
FC_READ_DISCRETE_INPUTS = 0x02
FC_WRITE_SINGLE_COIL = 0x05

MAX_READ_BITS = 2000  # Modbus spec limit for FC 0x01 / 0x02

_MBAP = struct.Struct(">HHHB")  # transaction id, protocol id, length, unit id

EXCEPTION_CODES = {
    0x01: "illegal function",
    0x02: "illegal data address",
    0x03: "illegal data value",
    0x04: "server device failure",
    0x05: "acknowledge",
    0x06: "server device busy",
    0x0A: "gateway path unavailable",
    0x0B: "gateway target device failed to respond",
}


class LogoModbusError(Exception):
    """Raised for any communication or protocol error."""


class LogoModbusExceptionResponse(LogoModbusError):
    """The device answered with a Modbus exception response."""

    def __init__(self, function: int, code: int) -> None:
        """Initialize the exception."""
        self.function = function
        self.code = code
        text = EXCEPTION_CODES.get(code, "unknown exception")
        super().__init__(
            f"Modbus exception {code:#04x} ({text}) for function {function:#04x}"
        )


class LogoModbusClient:
    """Tiny Modbus TCP client: one request at a time, reconnect on demand."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        *,
        unit_id: int = 1,
        timeout: float = 5.0,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._transaction_id = 0

    @property
    def host(self) -> str:
        """Return the host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the port."""
        return self._port

    @property
    def connected(self) -> bool:
        """Return True if a TCP connection is open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the TCP connection (no-op if already connected)."""
        async with self._lock:
            await self._ensure_connected()

    async def close(self) -> None:
        """Close the TCP connection."""
        async with self._lock:
            await self._close_locked()

    async def read_coils(self, address: int, count: int) -> list[bool]:
        """Read `count` coils starting at `address` (FC 0x01)."""
        return await self._read_bits(FC_READ_COILS, address, count)

    async def read_discrete_inputs(self, address: int, count: int) -> list[bool]:
        """Read `count` discrete inputs starting at `address` (FC 0x02)."""
        return await self._read_bits(FC_READ_DISCRETE_INPUTS, address, count)

    async def write_coil(self, address: int, value: bool) -> None:
        """Write a single coil (FC 0x05)."""
        _check_address(address)
        payload = struct.pack(">HH", address, 0xFF00 if value else 0x0000)
        response = await self._request(FC_WRITE_SINGLE_COIL, payload)
        if response != payload:
            raise LogoModbusError(
                f"Unexpected echo for write coil {address}: {response.hex()}"
            )

    async def _read_bits(self, function: int, address: int, count: int) -> list[bool]:
        _check_address(address)
        if not 1 <= count <= MAX_READ_BITS:
            raise ValueError(f"count must be 1..{MAX_READ_BITS}, got {count}")
        response = await self._request(function, struct.pack(">HH", address, count))
        byte_count = (count + 7) // 8
        if len(response) != 1 + byte_count or response[0] != byte_count:
            raise LogoModbusError(
                f"Unexpected response length for function {function:#04x}: "
                f"{response.hex()}"
            )
        data = response[1:]
        return [bool(data[i // 8] >> (i % 8) & 1) for i in range(count)]

    async def _request(self, function: int, payload: bytes) -> bytes:
        """Send one request and return the PDU data (without function code)."""
        async with self._lock:
            await self._ensure_connected()
            assert self._reader is not None and self._writer is not None

            self._transaction_id = (self._transaction_id + 1) & 0xFFFF
            tid = self._transaction_id
            pdu = bytes([function]) + payload
            frame = _MBAP.pack(tid, 0, len(pdu) + 1, self._unit_id) + pdu

            try:
                self._writer.write(frame)
                await asyncio.wait_for(self._writer.drain(), self._timeout)
                response = await asyncio.wait_for(
                    self._read_response(tid), self._timeout
                )
            except (TimeoutError, OSError, asyncio.IncompleteReadError) as err:
                await self._close_locked()
                raise LogoModbusError(
                    f"Communication with {self._host}:{self._port} failed: "
                    f"{err!r}"
                ) from err
            except LogoModbusError:
                await self._close_locked()
                raise

        resp_function = response[0]
        if resp_function == function | 0x80:
            code = response[1] if len(response) > 1 else 0
            raise LogoModbusExceptionResponse(function, code)
        if resp_function != function:
            raise LogoModbusError(
                f"Unexpected function code {resp_function:#04x} "
                f"(expected {function:#04x})"
            )
        return response[1:]

    async def _read_response(self, tid: int) -> bytes:
        assert self._reader is not None
        while True:
            header = await self._reader.readexactly(_MBAP.size)
            r_tid, proto, length, _unit = _MBAP.unpack(header)
            if proto != 0 or length < 2 or length > 260:
                raise LogoModbusError(f"Invalid MBAP header: {header.hex()}")
            pdu = await self._reader.readexactly(length - 1)
            if r_tid == tid:
                return pdu
            # A stale answer to an earlier (timed out) request: drop it.
            _LOGGER.debug("Discarding response with transaction id %s", r_tid)

    async def _ensure_connected(self) -> None:
        if self.connected:
            return
        await self._close_locked()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
        except (TimeoutError, OSError) as err:
            raise LogoModbusError(
                f"Cannot connect to {self._host}:{self._port}: {err!r}"
            ) from err
        _LOGGER.debug("Connected to %s:%s", self._host, self._port)

    async def _close_locked(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), self._timeout)
        except (TimeoutError, OSError):
            pass


def _check_address(address: int) -> None:
    if not 0 <= address <= 0xFFFF:
        raise ValueError(f"address must be 0..65535, got {address}")
