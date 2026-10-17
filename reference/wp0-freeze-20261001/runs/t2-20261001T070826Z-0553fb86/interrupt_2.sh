#!/bin/bash
set -u

rm -f "/tmp/wolfboot-t2-2.uart"
renode --disable-xwt -P 55162 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T070826Z-0553fb86/interrupt_2.resc" >/tmp/renode-t2.log 2>&1 &
pid=$!
for _ in $(seq 1 30); do
  [ -e "/tmp/wolfboot-t2-2.uart" ] && break
  sleep 1
done
sleep 2
ret=$(timeout 20 tools/test-expect-version/test-expect-version "/tmp/wolfboot-t2-2.uart" || true)
echo "version=$ret"
if [ "$ret" = "1" ]; then echo "Factory img: OK"; fi
ret2=$(timeout 8 tools/test-expect-version/test-expect-version "/tmp/wolfboot-t2-2.uart" || true)
echo "version2=$ret2"
if [ "$ret2" = "2" ]; then echo "Update: OK"; fi
if command -v nc >/dev/null; then
  (echo; echo quit; echo) | nc -q 1 localhost 55162 >/dev/null || true
fi
kill "$pid" >/dev/null 2>&1 || true
exit 0
