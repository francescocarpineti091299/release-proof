#!/bin/bash
set -u
cp "/home/carpy/.cache/firmware-migration-assurance/workbench/wolfBoot/config/examples/nrf52840.config" .config
make keysclean
make keytools
make -C tools/test-expect-version
make clean && make SIGN=ECC256 || exit 2
make /tmp/renode-test-update.bin SIGN=ECC256 || exit 2
cp wolfboot.elf /tmp/renode-wolfboot.elf
cp test-app/image_v1_signed.bin /tmp/renode-test-v1.bin
cp test-app/renode-test-update.bin /tmp/renode-test-update.bin

rm -f "/tmp/wolfboot-t2-1.uart"
renode --disable-xwt -P 55161 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T070826Z-0553fb86/interrupt_1.resc" >/tmp/renode-t2.log 2>&1 &
pid=$!
for _ in $(seq 1 30); do
  [ -e "/tmp/wolfboot-t2-1.uart" ] && break
  sleep 1
done
sleep 2
ret=$(timeout 20 tools/test-expect-version/test-expect-version "/tmp/wolfboot-t2-1.uart" || true)
echo "version=$ret"
if [ "$ret" = "1" ]; then echo "Factory img: OK"; fi
ret2=$(timeout 8 tools/test-expect-version/test-expect-version "/tmp/wolfboot-t2-1.uart" || true)
echo "version2=$ret2"
if [ "$ret2" = "2" ]; then echo "Update: OK"; fi
if command -v nc >/dev/null; then
  (echo; echo quit; echo) | nc -q 1 localhost 55161 >/dev/null || true
fi
kill "$pid" >/dev/null 2>&1 || true
exit 0
