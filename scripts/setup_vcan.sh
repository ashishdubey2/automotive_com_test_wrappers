#!/usr/bin/env bash
set -euo pipefail

interface="${1:-vcan0}"

if ! command -v ip >/dev/null 2>&1; then
    echo "iproute2 is required (the 'ip' command was not found)." >&2
    exit 1
fi

if ! command -v modprobe >/dev/null 2>&1; then
    echo "modprobe is required to load the Linux vcan driver." >&2
    exit 1
fi

if ip link show dev "$interface" >/dev/null 2>&1; then
    echo "Interface '$interface' already exists; refusing to modify it." >&2
    exit 1
fi

modprobe vcan
ip link add dev "$interface" type vcan
if ! ip link set dev "$interface" up; then
    ip link del dev "$interface"
    echo "Failed to bring '$interface' up; removed the interface created here." >&2
    exit 1
fi

echo "Created virtual CAN interface '$interface'."
echo "Remove it when finished with: ip link del dev $interface"
