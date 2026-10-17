#!/bin/bash
set -u
echo reuse
rm -f "/tmp/wolfboot-t2-copy-2.uart" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_2.bin" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_2.json"
renode --disable-xwt -P 55192 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/copy_sector_2.resc" >/tmp/renode-t2-copy.log 2>&1 &
pid=$!
python3 "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/harness/o06_uart_watch.py" "/tmp/wolfboot-t2-copy-2.uart" "$pid" "55192" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_2.bin" "/mnt/c/Users/carpy/Desktop/ProgettiPersonali/firmware-migration-assurance/wp0/runs/t2-20261001T090819Z-3f080e11/uart_2.json"
wait "$pid" >/dev/null 2>&1 || true
exit 0
