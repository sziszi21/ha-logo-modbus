"""A tiny fake LOGO! Modbus TCP server for tests.

Emulates the LOGO! program `Qn = Mn OR physical[n]`.
"""

from __future__ import annotations

import asyncio
import struct

ADDR_OUTPUTS = 8192
ADDR_FLAGS = 8256
NUM_Q = 20
NUM_I = 24
NUM_M = 64


class FakeLogo:
    """Fake LOGO! with I1..I24, Q1..Q20, M1..M64."""

    def __init__(self) -> None:
        self.inputs = [False] * NUM_I
        self.flags = [False] * NUM_M
        self.physical = [False] * NUM_Q  # "physical logic" ORed into Q
        self.requests: list[tuple[int, int, int]] = []  # (function, address, value/count)
        self.unit_ids: list[int] = []
        self.silent = False  # do not answer (timeout tests)
        self.reject_writes = False  # answer FC 05 with "server device failure"
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self.port = 0

    @property
    def outputs(self) -> list[bool]:
        return [self.flags[i] or self.physical[i] for i in range(NUM_Q)]

    async def start(self, port: int = 0) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.drop_clients()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def drop_clients(self) -> None:
        for writer in list(self._writers):
            writer.close()
        self._writers.clear()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while True:
                header = await reader.readexactly(7)
                tid, proto, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                self.unit_ids.append(unit)
                if self.silent:
                    continue
                resp = self._process(pdu)
                writer.write(struct.pack(">HHHB", tid, proto, len(resp) + 1, unit) + resp)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    def _process(self, pdu: bytes) -> bytes:
        function = pdu[0]
        if function in (0x01, 0x02):
            address, count = struct.unpack(">HH", pdu[1:5])
            self.requests.append((function, address, count))
            bits = self._read_bits(function, address, count)
            if bits is None:
                return bytes([function | 0x80, 0x02])
            data = bytearray((count + 7) // 8)
            for i, bit in enumerate(bits):
                if bit:
                    data[i // 8] |= 1 << (i % 8)
            return bytes([function, len(data)]) + bytes(data)
        if function == 0x05:
            address, value = struct.unpack(">HH", pdu[1:5])
            self.requests.append((function, address, value))
            if self.reject_writes:
                return bytes([function | 0x80, 0x04])
            if not ADDR_FLAGS <= address < ADDR_FLAGS + NUM_M or value not in (0, 0xFF00):
                return bytes([function | 0x80, 0x02])
            self.flags[address - ADDR_FLAGS] = value == 0xFF00
            return pdu[:5]
        return bytes([function | 0x80, 0x01])

    def _read_bits(self, function: int, address: int, count: int) -> list[bool] | None:
        if function == 0x02:
            if address + count > NUM_I:
                return None
            return self.inputs[address : address + count]
        if ADDR_OUTPUTS <= address and address + count <= ADDR_OUTPUTS + NUM_Q:
            start = address - ADDR_OUTPUTS
            return self.outputs[start : start + count]
        if ADDR_FLAGS <= address and address + count <= ADDR_FLAGS + NUM_M:
            start = address - ADDR_FLAGS
            return self.flags[start : start + count]
        return None
