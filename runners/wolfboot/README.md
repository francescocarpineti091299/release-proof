# wolfBoot runner (WS-A)

HTTP runner for the `wolfboot` template family of `profiles/test_catalog.yaml`, used by profile
`profiles/nrf52840-wolfboot-pqc.yaml` (change `ecdsa_p256_to_mldsa87`). Built on the shared
stdlib framework `runners/common/rp_runner` (protocol: `schemas/runner_event.schema.json`).

Image: `releaseproof/runner-wolfboot:0.1.0` (linux/amd64). Everything is fetched at image build
time; a job needs no network.

## Build, run, smoke

From the repository root:

```powershell
docker build -f runners/wolfboot/Dockerfile -t releaseproof/runner-wolfboot:0.1.0 .
docker run -d --name rp-wolfboot -v C:\path\to\data:/data -p 18081:8080 releaseproof/runner-wolfboot:0.1.0
backend\.venv\Scripts\python.exe runners\wolfboot\smoke.py --data-dir C:\path\to\data
```

`smoke.py` POSTs `/execute` with all 8 templates, validates every NDJSON event (as
`{"event": ...}`) against `schemas/runner_event.schema.json`, checks seq/run_id/done invariants,
that every template has a `test_result`, that every referenced observation/artifact exists, that
each test emitted the facts of the WORKSTREAMS table, and (with `--data-dir`) that every artifact
file on the host matches its announced sha256. `--save run.ndjson` keeps the raw stream.

Offline unit tests of the UART/classification logic:

```powershell
$env:PYTHONPATH="runners\common;runners\wolfboot"
backend\.venv\Scripts\python.exe -m unittest discover -s runners\wolfboot\tests -v
```

The build context is limited by `Dockerfile.dockerignore` to `runners/common/rp_runner/*.py` and
`runners/wolfboot/rp_wolfboot/`. The container runs as root so that the shared `/data` volume is
writable whatever its owner; the baked source tree is `chmod a-w` and never used as a build dir.

## Pins (verified at image build, `test` fails the build on mismatch)

| Item | Pin |
|---|---|
| Base image | `antmicro/renode:1.16.1` (Ubuntu 22.04, Renode v1.16.1.16973, .NET 8) |
| Arm GNU Toolchain | 14.2.rel1 x86_64 → `arm-none-eabi-gcc 14.2.1 20241119 (Build arm-14.52)`; tarball sha256 `62a63b981fe391a9cbad7ef51b17e49aeaa3e7b0d029b36ca1e9c3b2a9b78823` checked against Arm's `.sha256asc` |
| wolfBoot | `https://github.com/wolfSSL/wolfBoot` @ `4c79eee999b7083743811f37928322fe78b9fdb1` (shallow fetch by sha) |
| wolfSSL (`lib/wolfssl`) | `4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f` (asserted equal to the gitlink recorded by the wolfBoot commit) |
| Host tools | GNU Make 4.3, git 2.34.1, gcc 11.4.0 (keytools), Python 3.10.12 |

Other submodules (wolfTPM, wolfPKCS11, wolfHSM, …) are not fetched: the nRF52840 config does not
use them. Host keytools (`tools/keytools/{keygen,sign}`) are pre-built in the image; in each
per-run copy `make keytools` is a no-op (timestamps preserved).

## What a run does

Engine phases: PREPARING → DISCOVERY → BUILD_SIGN → EMULATION_TESTS.

* **Isolation**: each build variant gets a fresh copy of `/opt/wolfboot` (without `.git`) under
  the per-run `ctx.workdir` (`/tmp/rp-<run_id>-*`, deleted at the end). Renode `HOME`/`TMPDIR` are
  per run. No fixed `/tmp` file, no TCP port (Renode runs `--console` on a pipe and ends with `quit`).
* **Builds** (memoised in `ctx.cache`, steps of `tools/scripts/renode-test-update.sh` as argv lists,
  serial `make` like the script): `.config` ← `config/examples/nrf52840.config`, `make keysclean`,
  `make keytools`, `make clean`, `make <args>`, `make <run>/out/renode-test-update.bin TMP=<run>/out <args>`
  (the Makefile's own recipe: signs v2, 0xFF fill to POFF=262139, appends `pBOOT`).
  * deployed `ecc`: `SIGN=ECC256`
  * candidate `mldsa`: `SIGN=ML_DSA ML_DSA_LEVEL=5 WOLFBOOT_SMALL_STACK=0 IMAGE_SIGNATURE_SIZE=4627 IMAGE_HEADER_SIZE=12288 WOLFBOOT_SECTOR_SIZE=0x3000`
  * hybrid `dual` (O05 only, inside `run()`): `SIGN=ECC256 SIGN_SECONDARY=ML_DSA ML_DSA_LEVEL=5 WOLFBOOT_SMALL_STACK=0 IMAGE_HEADER_SIZE=12288 WOLFBOOT_SECTOR_SIZE=0x3000`
* **Emulation**: a generated `run.resc` per test (artifact), same sequence as
  `tools/renode/nrf52840_wolfboot.resc` but with deterministic virtual time:
  load `wolfboot.elf` + image at `0x20000`, `emulation RunFor 2 s`, then (update tests) switch the
  UART file backend, `cpu Reset`, load the update image at `0x60000`, `emulation RunFor 4 s`, `quit`.
  UART goes to files with `uart0 CreateFileBackend`; wall-clock limit 120 s per emulation.
* **UART parsing** is done on the raw bytes: the test app writes `0x2A` + 4-byte big-endian version
  (`test-app/app_nrf52.c`); the wolfBoot text (`DEBUG_UART=1`) is kept for refusal markers.

## Templates and observations

| Template | test_id | Observations (fact = value) | Outcome rule |
|---|---|---|---|
| `wolfboot.discover` | D01 | `bootloader_commit`, `crypto_commit` (git rev-parse in the baked tree), `partition_layout` (ints from the pinned `nrf52840.config`) | PASS if recorded and equal to the profile pins |
| `wolfboot.self_update_capability` | E11 | `bootloader_field_update` (source inspection) | PASS if SUPPORTED/UNSUPPORTED, INCONCLUSIVE if UNKNOWN |
| `wolfboot.boot_current` | E01 (+E08) | `boot_outcome`, `observed_version`, `signed_image_size_bytes`, `bootloader_size_bytes`, `public_key_sha256`; E08 `update_outcome` (ECC v1→v2) | PASS iff v1 frame and update APPLIED |
| `wolfboot.boot_candidate` | E02 (+E04, E05) | same five facts on `candidate_state`; E04 `image_header`; E05 `layout_fit` | PASS iff v1 frame and signed ≤ partition |
| `wolfboot.tampered_image_rejected` | E03 | `auth_negative` | PASS iff REJECT |
| `wolfboot.cross_generation_update` | X01 | `cross_update_outcome` | PASS iff REJECTED |
| `wolfboot.candidate_rejects_classical` | P01 | `classical_image_on_candidate` | PASS iff REJECT |
| `wolfboot.dual_signature_build` | O05 | `dual_signature_build` | FAIL if BUILD_FAILED (a measured result), INCONCLUSIVE if BUILT_NOT_BOOTED |

Decision rules (no default verdicts, a timeout is never a rejection):

* `boot_outcome`: BOOT_OK only with a version frame; FAIL only with an explicit refusal line
  (`wolfBoot: PANIC!`, `Boot failed…`, `No boot option available`); otherwise UNKNOWN.
  `Partition 1 header magic … invalid` is printed on every boot with an empty update partition and is
  deliberately **not** a refusal marker.
* `auth_negative` / `classical_image_on_candidate`: ACCEPT if any version frame; REJECT only with an
  explicit refusal line **and** no version frame; otherwise UNKNOWN (→ INCONCLUSIVE). This fixes the
  POC T3 check that counted an empty/timeout capture as REJECT.
* staged update (E08, X01): APPLIED if the new version's frame or `Booting version: 0x2` appears
  after the reset; NOT_APPLIED / REJECTED only if the version that ran before the reset is observed
  again after it, with no trace of the new version; otherwise UNKNOWN.
* E03 flips one payload byte (offset `header + fw_size/2`) of the deployed signed v1 image.
* X01 = deployed ECC bootloader + ECC v1 in the boot partition + candidate ML-DSA-87 v2 (12288-byte
  header) in the update partition with the same layout as the Makefile recipe (0xFF fill,
  `pBOOT` at partition offset 262139). Both builds have identical partition addresses and size
  (boot `0x20000`, update `0x60000`, swap `0xE0000`, size `0x40000`, read from each build's
  generated `include/target.h`); only the sector size (0x1000 vs 0x3000) and the header size
  (256 vs 12288) differ. With `NVM_FLASH_WRITEONCE=0` the partition trailer sits at the partition
  end, independent of the sector size, so the deployed bootloader does see the staged update. The
  Python-built image is self-checked byte-for-byte against the make-built ECC update image
  (`layout_comparison.json`).
* P01 has two cells, both on the candidate ML-DSA bootloader: A = the deployed ECC256 v1 artifact
  as shipped (256-byte header); B = the candidate payload ECC256-signed with the deployed key but
  with the candidate's 12288-byte header (`keytools/sign --ecc256 --sha256`), so that only the
  signature algorithm differs. Value: ACCEPT if any cell boots; REJECT if A is refused and B is not
  accepted.
* E11 rule: SUPPORTED if an nRF52 self-update example config or an nRF52 HAL self-update path
  exists; UNSUPPORTED if neither exists and the board config keeps `RAM_CODE=0` (the self-update
  path in `src/update_flash.c` is compiled only under `#ifdef RAM_CODE`); else UNKNOWN. Inspected
  files/lines are in the locator and in `discovery/e11_self_update_scan.json`.
* E05 `boot_slot_capacity` = `WOLFBOOT_PARTITION_SIZE` of the build (same operand as the frozen
  projection). The signer's tighter bound (partition − 1 sector = 249856 B for the candidate) is not
  emitted as a fact.

## Reference run (2026-10-17, Docker Desktop, 8 vCPU)

All 8 templates ≈ 67 s wall (builds ≈ 8.5 s, each emulation 6–13 s). Results consistent with the WP0
freeze:

| Fact | Observed | Frozen WP0 |
|---|---|---|
| ECC256 signed v1 / bootloader | 840 B / 23652 B | 840 / 23652 |
| ML-DSA-87 signed v1 / bootloader | 12876 B / 22840 B | 12876 / 22840 |
| ML-DSA header span / partition | 12288 B / 262144 B | 12288 / 262144 |
| E01 / E08 | frame `2a 00 00 00 01`, then `2a 00 00 00 02` after reset (APPLIED) | Factory/Update OK |
| E02 | frame `2a 00 00 00 01` | boot observed |
| E03 | `Checking integrity...Boot failed: Hdr 1, Hash 0, Sig 0` … `wolfBoot: PANIC!`, no frame → REJECT | REJECT (weak check) |
| X01 | `Update type invalid 0xB01!=0x200`, frame 1 before and after reset → REJECTED | — |
| P01 | A: `Boot failed: Hdr 1, Hash 0, Sig 0` + PANIC; B: `Verifying signature...Boot failed: Hdr 1, Hash 1, Sig 0` + PANIC → REJECT | — |
| O05 | `include/image.h:88:9: error: "wolfBoot_verify_signature_primary" redefined [-Werror]`, `make: *** [Makefile:941: src/string.o]` → BUILD_FAILED | BUILD_FAILED (same error) |
| E11 | UNSUPPORTED (no nRF52 self-update config/HAL path, `RAM_CODE=0`) | UNSUPPORTED |

Keys are regenerated on every run (`make keysclean`), so `public_key_sha256` differs between runs
by design; sizes and UART text are identical run to run.

## Limitations

* Renode models nRF52840 flash as plain memory; NVMC registers are unimplemented (READY reads 1), so
  erase/write timing and power-loss faults are not reproduced. Flash starts zero-filled.
* Fixed virtual time windows (2 s boot, 4 s update) — enough by a wide margin for these images; a
  slower image would show up as UNKNOWN/INCONCLUSIVE, never as a rejection.
* X01's rejection on this commit happens at the image-type check (`Update type invalid`), before any
  signature verification; P01 cell A fails at the integrity check because of the header-size
  mismatch, cell B is the signature-level refusal.
* O05 only builds; a successful hybrid build would be reported BUILT_NOT_BOOTED (not booted).
* The interrupted-update (non-atomic window, E12) is not implemented.
* One run at a time per runner (server returns 409 when busy).
