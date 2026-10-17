#!/bin/bash
set -u
echo reuse
rm -f "/tmp/wolfboot-t2-event-2.uart" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T082614Z-11ae80a6/uart_2.bin"
renode --disable-xwt -P 55182 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T082614Z-11ae80a6/interrupt_event_2.resc" >/tmp/renode-t2-event.log 2>&1 &
pid=$!
python3 - "/tmp/wolfboot-t2-event-2.uart" "$pid" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T082614Z-11ae80a6/uart_2.bin" <<'PY'
import os
import signal
import sys
import time

uart, pid_text, out = sys.argv[1], sys.argv[2], sys.argv[3]
pid = int(pid_text)
deadline = time.time() + 120


def complete_frames(buf):
    count = 0
    index = 0
    while index < len(buf):
        if buf[index] == 0x2A and index + 4 < len(buf):
            count += 1
            index += 5
            continue
        index += 1
    return count


fd = None
buf = bytearray()
while time.time() < deadline and fd is None:
    if os.path.exists(uart):
        try:
            fd = os.open(uart, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(0.05)
    else:
        time.sleep(0.05)
while fd is not None and time.time() < deadline:
    try:
        chunk = os.read(fd, 4096)
    except BlockingIOError:
        chunk = b""
    except OSError:
        break
    if chunk:
        buf.extend(chunk)
    if complete_frames(buf) >= 2:
        break
    time.sleep(0.05)
with open(out, "wb") as handle:
    handle.write(buf)
if fd is not None:
    os.close(fd)
try:
    os.kill(pid, signal.SIGTERM)
except ProcessLookupError:
    pass
PY
wait "$pid" >/dev/null 2>&1 || true
exit 0
