# Virtual communication testing

The virtual suite sends test messages through real Linux SocketCAN (`vcan`)
and real localhost TCP/UDP sockets. LIN uses an in-process pair of endpoints.
It validates protocol encoding, message contents, framing, and receive logic;
it does not validate a physical ECU, PEAK adapter, bus wiring, or electrical
behavior.

## Start the virtual CAN interface

`vcan` is a Linux kernel virtual CAN network driver. Create and bring up
`vcan0` once, using elevated privileges:

```sh
sudo bash scripts/setup_vcan.sh
```

The script refuses to modify an existing interface. It creates `vcan0` only
when no interface with that name exists. Remove the interface when finished:

```sh
sudo ip link del dev vcan0
```

Install the Python package and optional PEAK/CAN dependencies if needed:

```sh
python -m pip install -e ".[peak]"
```

Run all tests:

```sh
python -m unittest discover -s tests -v
```

The CAN integration test is skipped when `vcan0` is not up. The localhost
TCP/UDP, SOME/IP, and software LIN tests do not need root or PEAK hardware.

## What is sent and received

### CAN on `vcan0`

Two separate SocketCAN sockets use the same kernel `vcan0` interface. The
sender sends a standard frame with arbitration ID `0x321` and eight data bytes:

| Field | Value |
|---|---|
| Arbitration ID | `0x321` |
| DLC | `8` |
| Data byte 0 | `0x10` |
| Data byte 1 | `0x20` |
| Data byte 2 | `0x30` |
| Data byte 3 | `0x40` |
| Data byte 4 | `0x50` |
| Data byte 5 | `0x60` |
| Data byte 6 | `0x70` |
| Data byte 7 | `0x80` |

The receiving socket checks the ID, standard/extended flag, remote-frame flag,
DLC, and all data bytes. SocketCAN exposes CAN frame fields to this test; it
does not expose physical SOF, CRC, ACK, or bus timing bits.

### LIN software loopback

`VirtualLinBus.create_pair()` creates two in-process endpoints. When one sends
a `LinFrame`, the other receives the complete frame object. The test verifies
the protected ID, payload, checksum type, and checksum for enhanced and classic
frames. Logical frames remain separate queue entries; the receiver can select
an identifier and later retrieve other pending identifiers.

The LIN wrapper models identifier parity and checksum, but this software pair
does not produce LIN break or sync fields, bit timing, dominant/recessive
levels, or electrical traffic. Use `PeakLinTransport` and PLIN-USB for those
hardware-level checks.

One enhanced LIN frame used in the test has this logical wire layout:

| Order | Byte/signal | Value |
|---:|---|---|
| 1 | Break | Start-of-frame low pulse; not represented as a data byte |
| 2 | Sync byte | `0x55`; not represented in `LinFrame` |
| 3 | Protected identifier (PID) | `0x92` (6-bit ID `0x12` plus parity bits) |
| 4 | Data byte 0 | `0x10` |
| 5 | Data byte 1 | `0x20` |
| 6 | Data byte 2 | `0x30` |
| 7 | Enhanced checksum | `0x0D` |
| 8 | Inter-frame space | Bus timing, not a data byte |

The paired software endpoints deliver each complete logical frame as a
separate queued message; they do not synthesize the break, sync, or inter-frame
timing signals.

### TCP and UDP

TCP tests bind an echo server to an ephemeral `127.0.0.1` port. TCP is a byte
stream and has no inherent message boundaries; the test server reads the
known test-message size, and the client uses `receive_exactly()` to read that
many bytes. The basic TCP payload is five application bytes: `10 20 30 40 50`
(byte offsets 0 through 4). UDP tests use an echo server on localhost; each
send and receive is one datagram, so the tested datagram boundary is the
message boundary. The test sends `A1 A2` as one datagram and `B1 B2 B3` as a
second datagram, then checks that each is received separately.

### SOME/IP wire bytes

SOME/IP's fixed header is 16 bytes. Multibyte values use network byte order:

| Byte offsets | Size | Field |
|---|---:|---|
| 0-1 | 2 | Service ID |
| 2-3 | 2 | Method ID |
| 4-7 | 4 | Length (the 8 bytes from offset 8 plus payload length) |
| 8-9 | 2 | Client ID |
| 10-11 | 2 | Session ID |
| 12 | 1 | Protocol version |
| 13 | 1 | Interface version |
| 14 | 1 | Message type |
| 15 | 1 | Return code |
| 16 onward | Variable | Payload |

For the TCP SOME/IP test, the length field also separates messages on the byte
stream: read the first 8 bytes, interpret bytes 4-7 as the length, then read
that many remaining bytes. UDP carries each full SOME/IP message as one
datagram. The tests verify the exact header bytes and every decoded message
field, as well as the payload.
