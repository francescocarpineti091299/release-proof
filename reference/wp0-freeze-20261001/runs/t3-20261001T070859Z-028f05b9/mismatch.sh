#!/bin/bash
set -u
rm -f "/tmp/wolfboot-t3.uart"
renode --disable-xwt -P 55170 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t3-20261001T070859Z-028f05b9/mismatch.resc" >/tmp/renode-t3.log 2>&1 &
pid=$!
for _ in $(seq 1 30); do
  [ -e "/tmp/wolfboot-t3.uart" ] && break
  sleep 1
done
sleep 2
ret=$(timeout 25 "/home/carpy/.cache/firmware-migration-assurance/workbench/wolfBoot/tools/test-expect-version/test-expect-version" "/tmp/wolfboot-t3.uart" || true)
echo "version=$ret"
if [ "$ret" = "1" ]; then echo "Factory img: OK"; fi
if command -v nc >/dev/null; then
  (echo; echo quit; echo) | nc -q 1 localhost 55170 >/dev/null || true
fi
kill "$pid" >/dev/null 2>&1 || true
exit 0
