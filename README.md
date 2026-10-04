# Automotive Communication Test Wrappers

A small Python package for exercising embedded automotive communication
modules over CAN, J1939, LIN, TCP, UDP, and SOME/IP. The wrappers provide
protocol encoding, transport interfaces, and explicit send/receive operations;
they do not assume a particular vehicle interface or ECU.

## Install

```sh
python -m pip install -e .
```

The generic wrappers use only the Python standard library. Optional PEAK
adapters are available for PCAN and PLIN devices on Linux.

## Examples

### CAN and J1939

Pass a CAN transport adapter with `send(frame)` and `receive(timeout=...)`
methods to `CanTester`:

```python
from automotive_com_test_wrappers.can import CanFrame, CanTester

tester = CanTester(can_transport)
tester.transmit(CanFrame(arbitration_id=0x123, data=b"\x01\x02"))
received = tester.receive(timeout=1.0)
```

`J1939Tester` uses the same transport and encodes/decodes 29-bit J1939
identifiers, including PDU1 destination addresses.

### LIN

Implement `LinTransport.send(frame)` and `LinTransport.receive(identifier,
timeout=...)`. `LinTester` calculates protected identifiers and classic or
enhanced checksums, and validates received frames.

### PEAK PCAN and PLIN on Linux

Install the package with its optional PEAK dependencies:

```sh
python -m pip install -e ".[peak]"
```

Install PEAK's Linux CAN and LIN drivers separately. The PCAN Linux driver
exposes CAN devices through SocketCAN; configure the bitrate and interface
state with the Linux network tools for your interface (commonly `can0`) before
opening the adapter. The LIN driver exposes character devices such as
`/dev/plin0`; make sure the user running the test has permission to access it.

```python
from automotive_com_test_wrappers.can import CanFrame, CanTester
from automotive_com_test_wrappers.lin import LinTester
from automotive_com_test_wrappers.peak import PeakCanTransport, PeakLinTransport

with PeakCanTransport(channel="can0") as can_transport:
    can_tester = CanTester(can_transport)
    can_tester.transmit(CanFrame(0x123, b"\x01\x02"))

with PeakLinTransport(interface="/dev/plin0", baudrate=19200) as lin_transport:
    lin_tester = LinTester(lin_transport)
    lin_tester.transmit(identifier=0x12, data=b"\x01\x02")
```

`PeakLinTransport` defaults to LIN master mode. Pass `mode="slave"` to operate
as a slave. The adapter communicates with the PEAK Linux LIN character-device
API; install the PEAK LIN driver before use. Hardware integration tests require
the corresponding PEAK adapter and bus.

### TCP and UDP

```python
from automotive_com_test_wrappers.ethernet import TCPClient, UDPClient

with TCPClient("192.0.2.10", 5000) as tcp:
    tcp.send(b"request")
    response = tcp.receive(1024)

with UDPClient("192.0.2.10", 5001) as udp:
    udp.send(b"request")
    response = udp.receive(1024)
```

TCP is a byte stream: `receive(size)` may return fewer than `size` bytes.
Use `receive_exactly(size)` when a protocol requires an exact byte count.

### SOME/IP

`SomeIpMessage` handles SOME/IP header serialization and validation.
`SomeIpUdpClient` sends and receives one complete SOME/IP message per datagram;
`SomeIpTcpClient` reads the SOME/IP length field to assemble stream messages.
Service discovery and SOME/IP-TP are not included.

Run the test suite with:

```sh
python -m unittest discover -s tests -v
```

For Linux `vcan` and localhost integration testing (including test boundaries
and byte-level message layouts), see [Virtual communication testing](docs/virtual-testing.md).
