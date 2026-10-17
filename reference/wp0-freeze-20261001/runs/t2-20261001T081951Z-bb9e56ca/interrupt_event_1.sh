#!/bin/bash
set -u
cd "/home/carpy/.cache/firmware-migration-assurance/workbench/wolfBoot"
export WOLFBOOT_ROOT="$PWD"
cp config/examples/nrf52840.config .config
make keysclean
make keytools
make -C tools/test-expect-version
make clean && make SIGN=ECC256
make /tmp/renode-test-update.bin SIGN=ECC256
cp wolfboot.elf /tmp/renode-wolfboot.elf
cp test-app/image_v1_signed.bin /tmp/renode-test-v1.bin
cp test-app/renode-test-update.bin /tmp/renode-test-update.bin

rm -f "/tmp/wolfboot-t2-event-1.uart"
renode --disable-xwt -P 55181 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T081951Z-bb9e56ca/interrupt_event_1.resc" >/tmp/renode-t2-event.log 2>&1 &
pid=$!
python3 - "/tmp/wolfboot-t2-event-1.uart" "$pid" <<'PY'
import pathlib, sys, time
uart, pid = sys.argv[1], int(sys.argv[2])
path = pathlib.Path(uart)
deadline = time.time() + 40
while time.time() < deadline:
    if path.exists() and path.read_bytes().count(b"*") >= 2:
        break
    time.sleep(0.05)
import os, signal
os.kill(pid, signal.SIGTERM)
PY
wait "$pid" >/dev/null 2>&1 || true
exit 0
