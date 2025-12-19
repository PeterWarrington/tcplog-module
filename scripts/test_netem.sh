#!/usr/bin/env bash
set -euo pipefail

# scripts/test_netem.sh
# Created by GitHub CoPilot AI to simulate packet loss
# Usage: sudo ./scripts/test_netem.sh [LOSS_PERCENT] [DURATION_SECONDS] [MODE]
# MODE: loss (default) | reorder | dupacks
# Examples:
#  sudo ./scripts/test_netem.sh 10 30           # apply 10% loss on server egress
#  sudo ./scripts/test_netem.sh 0 30 reorder    # apply reordering to induce misordering/dup-ACKs
#  sudo ./scripts/test_netem.sh 1 30 dupacks    # small loss+reorder to provoke duplicate ACKs

LOSS=${1:-10}
DURATION=${2:-30}
MODE=${3:-loss}
PORT=5201
NS1=ns1
NS2=ns2
VETH1=veth-ns1
VETH2=veth-ns2
IP1=10.0.0.1/24
IP2=10.0.0.2/24

if [ "$(id -u)" -ne 0 ]; then
  echo "This script requires root. Re-run with sudo." >&2
  exit 1
fi

cleanup() {
  echo "Cleaning up..."
  set +e
  # remove tc qdisc
  ip netns exec ${NS2} tc qdisc del dev ${VETH2} root 2>/dev/null || true
  ip netns exec ${NS1} tc qdisc del dev ${VETH1} root 2>/dev/null || true
  # kill background processes started by the script
  if [ -n "${SERVER_PID:-}" ]; then kill ${SERVER_PID} 2>/dev/null || true; fi
  if [ -n "${CLIENT_PID:-}" ]; then kill ${CLIENT_PID} 2>/dev/null || true; fi
  if [ -n "${DMSG_PID:-}" ]; then kill ${DMSG_PID} 2>/dev/null || true; fi
  # delete namespaces
  ip netns delete ${NS1} 2>/dev/null || true
  ip netns delete ${NS2} 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Ensure no leftover namespaces
ip netns delete ${NS1} 2>/dev/null || true
ip netns delete ${NS2} 2>/dev/null || true

echo "Creating network namespaces and veth pair..."
ip netns add ${NS1}
ip netns add ${NS2}
ip link add ${VETH1} type veth peer name ${VETH2}
ip link set ${VETH1} netns ${NS1}
ip link set ${VETH2} netns ${NS2}

ip netns exec ${NS1} ip addr add ${IP1} dev ${VETH1}
ip netns exec ${NS2} ip addr add ${IP2} dev ${VETH2}

ip netns exec ${NS1} ip link set lo up
ip netns exec ${NS2} ip link set lo up
ip netns exec ${NS1} ip link set ${VETH1} up
ip netns exec ${NS2} ip link set ${VETH2} up

# simple reachability check
echo "Checking connectivity (should be reachable)..."
ip netns exec ${NS1} ping -c 2 ${IP2%/*}

case "${MODE}" in
  loss)
    echo "Applying netem loss=${LOSS}% on ${VETH2} inside ${NS2}..."
    ip netns exec ${NS2} tc qdisc add dev ${VETH2} root netem loss ${LOSS}%
    ;;
  reorder)
    echo "Applying netem reorder on ${VETH1} inside ${NS1} (delay 10ms, reorder 25% 50%) to induce misordering..."
    ip netns exec ${NS1} tc qdisc add dev ${VETH1} root netem delay 10ms reorder 25% 50%
    ;;
  dupacks)
    echo "Applying netem on ${VETH1} inside ${NS1}: delay 10ms reorder 25% 50% loss ${LOSS}% (to provoke duplicate ACKs)..."
    ip netns exec ${NS1} tc qdisc add dev ${VETH1} root netem delay 10ms reorder 25% 50% loss ${LOSS}%
    ;;
  *)
    echo "Unknown MODE='${MODE}'. Use 'loss', 'reorder' or 'dupacks'." >&2
    exit 2
    ;;
esac

# Start server: use iperf3 if available, else use Python
if command -v iperf3 >/dev/null 2>&1; then
  echo "Starting iperf3 server in ${NS2} (pid logged)..."
  ip netns exec ${NS2} iperf3 -s &
  # capture background PID safely (avoid set -u complaining if $! is unset)
  set +u
  SERVER_PID=$! || SERVER_PID=""
  set -u
  sleep 1
  echo "Starting iperf3 client from ${NS1} to ${IP2%/*} for ${DURATION}s..."
  ip netns exec ${NS1} iperf3 -c ${IP2%/*} -t ${DURATION}
  # iperf3 client runs in foreground; there's no background PID to capture
  CLIENT_PID=""
else
  echo "iperf3 not found. Using Python sockets as fallback."
  # Start a simple TCP server in NS2 that accepts and reads data (discard)
  ip netns exec ${NS2} python3 -u - <<PY &
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', ${PORT}))
s.listen(1)
print('Server listening')
conn, addr = s.accept()
print('Accepted', addr)
try:
    while True:
        data = conn.recv(65536)
        if not data:
            break
except Exception as e:
    print('Server exception', e)
conn.close()
s.close()
PY
  set +u
  SERVER_PID=""
  set -u
  sleep 1
  # Start client that sends continuously for DURATION seconds
  ip netns exec ${NS1} python3 -u - <<PY &
import socket, time
import sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("${IP2%/*}", ${PORT}))
end = time.time() + ${DURATION}
print('Client connected; sending until', end)
try:
    while time.time() < end:
        s.send(b'x' * 1400)
        # tiny pause to avoid pure busy loop
        time.sleep(0.001)
except Exception as e:
    print('Client exception', e)
s.close()
PY
  # capture background PID safely (avoid set -u complaining if $! is unset)
  set +u
  CLIENT_PID=$! || CLIENT_PID=""
  set -u
  # Wait for client to finish
  wait ${CLIENT_PID}
fi

# Wait a little so kernel logs are flushed
sleep 2

echo "Test complete. Cleaning up and exiting."
exit 0
