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

rm -f "/tmp/wolfboot-t2-copy-1.uart" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_1.bin" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_1.json"
renode --disable-xwt -P 55191 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/copy_sector_1.resc" >/tmp/renode-t2-copy.log 2>&1 &
pid=$!
python3 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/harness/o06_uart_watch.py" "/tmp/wolfboot-t2-copy-1.uart" "$pid" "55191" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_1.bin" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_1.json"
wait "$pid" >/dev/null 2>&1 || true
exit 0
