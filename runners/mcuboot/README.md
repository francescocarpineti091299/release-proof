# MCUboot runner (WS-B) — `releaseproof/runner-mcuboot:0.1.0`

HTTP runner (shared `rp_runner` framework) for the **`mcuboot`** template family of
`profiles/test_catalog.yaml`, used by profile `profiles/nrf52840-mcuboot-pqc.yaml`.
It **measures**: it builds MCUboot + a demo application with Zephyr for every run (with an
ephemeral key), signs images with the pinned `imgtool`, and boots them in Renode on an emulated
nRF52840. No verdicts are produced here.

## Build / run / smoke

```powershell
# from the repository root (build context = repo root)
docker build -f runners/mcuboot/Dockerfile -t releaseproof/runner-mcuboot:0.1.0 .

$d = "$env:TEMP\rpdata"; mkdir $d -Force
docker run -d --name rp-mcuboot -p 18080:8080 -v "${d}:/data" releaseproof/runner-mcuboot:0.1.0
backend\.venv\Scripts\python.exe runners\mcuboot\smoke.py --url http://localhost:18080 --data-dir $d
```

The image build ends with a full self-test run of all 7 templates (`python -m rp_mcuboot.warm`);
it fails the build only if the run cannot produce results. This also warms `ccache`, so the
per-run build (new key every run) takes ~20 s. A job needs no network (verified with
`docker run --network none ... python -m rp_mcuboot.warm`). Image size ≈ 3.8 GB.

`smoke.py` POSTs `/execute` with all templates, validates every NDJSON event against
`schemas/runner_event.schema.json` (`jsonschema` if importable — the backend venv has it — else a
built-in validator), checks the fact vocabulary of `docs/WORKSTREAMS.md`, observation/artifact
references and artifact SHA-256 on the host, and prints a summary. Exit 0 only if clean.

## How a run works

| Phase | What happens |
|---|---|
| PREPARING | checks toolchain/workspace/Renode/SVD/NVMC model; publishes `west manifest --freeze` + pip freeze |
| DISCOVERY | **D01**, **E11** — trigger the (memoised) per-run build, parse `zephyr.dts` / `.config` |
| BUILD_SIGN | ephemeral `ecdsa-p256` keys (`deployed`, `rotated`) with `imgtool keygen`; `west build --sysbuild` (MCUboot embeds the deployed key); `imgtool sign` v1 (slot 0), v2 (`--pad`, slot 1), tampered v2, v2 signed with the rotated key; 1 MiB flash images |
| EMULATION_TESTS | one Renode process per test (generated `.resc`, virtual time, wall-clock timeout) |

Build: one sysbuild per run under the run's `workdir` (`west build -d <workdir>/build`, app copied
to `<workdir>/src/app`); the baked workspace `/opt/zws` is never modified. The key is staged at a
fixed path (`/tmp/rp-mcuboot-key/`) so the generated Kconfig is identical across runs (ccache hits);
the server lock guarantees one run at a time.

Emulation (`rp_mcuboot/renode.py`): flash = 0xFF background + MCUboot at 0x0 + v1 signed image in
slot 0, loaded with `sysbus LoadBinary`. **Phase 1** (power-on) runs 3 s virtual time, UART →
`uart-phase1-power-on.log`. For staged-update tests, **phase 2**: the slot-1 image is written to
flash (as the running application would after a download), `machine Reset` (Renode keeps
`MappedMemory` content across reset), 5 s virtual time, UART → `uart-phase2-after-reset.log`.
`nvmc PageErases` is printed at the end (`renode.stdout.log`).

Demo app (`app/`, MIT): reads the MCUboot header and the KEYHASH TLV of the image it executes from
(the code partition) and prints
`RP-APP version=<maj>.<min>.<rev> build=<n> key=<sha256(pubkey)[0:8]> slot=0x<addr>`. The version
is therefore the one of the image actually booted, and the key prefix identifies the signer (it
equals the first 16 hex chars of `public_key_sha256`). One application binary is built; v1/v2 are
the same binary signed with different header versions.

## Templates and facts (per `docs/WORKSTREAMS.md`, MCUboot table)

| Template | test | Observations | Outcome rule |
|---|---|---|---|
| `mcuboot.discover` | D01 | `bootloader_commit`, `zephyr_commit` (git HEAD, cross-checked with `west list`), `partition_layout` (MCUboot `zephyr.dts`), `imgtool_key_types` (`imgtool keygen --help`) | PASS if all recorded |
| `mcuboot.bootloader_update_capability` | E11 | `bootloader_field_update` | UNSUPPORTED iff boot partition at 0x0, no `s0/s1/b0/mcuboot_secondary`-like partition, no first-stage bootloader in sysbuild config, `CONFIG_UPDATEABLE_IMAGE_NUMBER=1`; SUPPORTED only with partitions **and** first stage; else UNKNOWN (INCONCLUSIVE) |
| `mcuboot.boot_current` | E01 | `boot_outcome`, `observed_version` (major), `signed_image_size_bytes`, `bootloader_size_bytes`, `public_key_sha256`; plus **`OBS-E05-layout_fit`** `{signed_artifact_size, boot_slot_capacity}` (slot0 partition size) | BOOT_OK needs `Jumping to the first image slot` **and** a v1 marker with the deployed key |
| `mcuboot.signed_update` | E08 | `update_outcome` | APPLIED if phase 2 shows only v2 (deployed key); NOT_APPLIED if v1 kept running |
| `mcuboot.tampered_image_rejected` | E03 | `auth_negative` | REJECT only on positive evidence: `E: Image in the secondary slot is not valid!` and/or v1 marker after reset (and no v2) |
| `mcuboot.pqc_sign_attempt` | E02 | `pqc_signing {signing_result, algorithm, tool, message}` | tries `imgtool keygen -t ml-dsa-44/65/87` (and `sign` if a key is produced). REJECTED → **FAIL** (the PQC-signed candidate cannot be produced), OK → PASS |
| `mcuboot.cross_key_update` | X01 | `cross_update_outcome` (subject `transition`) | same rule as E03 with a v2 signed by the rotated key |

For E08/E03/X01 a decisive value also requires phase 1 to show v1 booting. No marker / Renode
wall-clock timeout → value `UNKNOWN`, outcome INCONCLUSIVE (`TIMEOUT`); Renode exiting non-zero →
ERROR (`TOOL_FAILURE`). **A UART timeout is never a REJECT** (verified by fault injection with a
1 ms phase 2).

Artifacts (under the run `artifact_dir`): `build/` (sysbuild log, mcuboot/app ELF+bin, both
`zephyr.dts`, `.config`s), `keys/` (public keys only, keygen logs), `images/` (signed images + sign
logs), `renode/` (repl, NVMC model, flash image, per-scenario `.resc`, UART captures, Renode log),
`pqc/` (ML-DSA attempt logs), `toolchain/` (west freeze/list, git heads, pip freeze, imgtool help).

## Pins (resolved at image build, exposed by `/health` and `done.source_pins`)

| Component | Pin |
|---|---|
| Zephyr | v4.2.0 = `413b789deb391d3a37d06b463288a5fe765ee57e` |
| MCUboot (Zephyr fork, manifest rev) | `4eba8087fa606db801455f14d185255bc8c49467` (imgtool 2.2.0) |
| hal_nordic | `9587b1dcb83d24ab74e89837843a5f7d573f7059` |
| cmsis / cmsis_6 | `512cc7e8…` / `06d952b6…` |
| mbedtls / tinycrypt / zcbor | `85440ef5…` / `1012a3eb…` / `9b07780a…` |
| Zephyr SDK | 0.17.4 minimal + `arm-zephyr-eabi` (gcc 12.2.0), sha256-checked |
| Renode | 1.16.1 portable dotnet (`1.16.1.17033`), sha256-checked |
| nRF52840 SVD | downloaded at image build, sha256 in `source_pins.nrf52840_svd_sha256` |
| Python | Ubuntu 24.04 python 3.12, west 1.4.0, MCUboot `scripts/requirements.txt` |

West uses a project allowlist (`cmsis, cmsis_6, hal_nordic, mcuboot, zcbor, mbedtls, tinycrypt`).
MCUboot ECDSA-P256 uses `CONFIG_BOOT_ECDSA_TINYCRYPT` (the default; tinycrypt is bundled in MCUboot's
`ext/`), so mbedtls/tinycrypt modules are kept only for safety.

Configuration: board `nrf52840dk/nrf52840`, `SB_CONFIG_BOOTLOADER_MCUBOOT`,
`SB_CONFIG_MCUBOOT_MODE_SWAP_USING_MOVE`, `SB_CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256`,
`CONFIG_MCUBOOT_SERIAL=n`. Partitions (from `zephyr.dts`): mcuboot 0x0+0xC000, slot0
0xC000+0x76000, slot1 0x82000+0x76000, storage 0xF8000+0x8000; 4 KiB pages.

## Decision log

1. **Board nRF52840 kept, swap-using-move works — no fallback needed.** Spike passed on the first
   attempt (MCUboot swap in ~12 s wall time). `direct-xip` / `overwrite-only` / STM32F4 fallbacks
   were not used.
2. **NVMC model written from scratch (MIT)** — `renode/rp_nrf52840_nvmc.cs`, compiled ad-hoc by
   Renode (`include @…cs`). Not derived from snhobbs/renode-nrf52840_flash (its license was not
   verified, so nothing was copied). It implements READY/READYNEXT=1, CONFIG, ERASEPAGE,
   ERASEPCR0/1, ERASEPAGEPARTIAL (full erase at once) and ERASEALL on the flash `MappedMemory`.
3. **Own platform file** `renode/nrf52840_rp.repl.in`, derived from Renode's MIT
   `platforms/cpus/nrf52840.repl`: SVD from a local file (upstream fetches it over HTTPS at load
   time → would need network in a job), NVMC model, FICR `CODEPAGESIZE=0x1000`/`CODESIZE=0x100` and
   UICR `PSELRESET[0/1]=18` tags (avoids the SoC init re-writing UICR and resetting). Unused
   peripherals (radio, TWI, SPI, I2S, PDM, extra timers/EGUs) are omitted.
4. **QSPI disabled** (`&qspi { status = "disabled"; }`) in both images instead of
   `/delete-node/` (keeps aliases valid); Renode has no nRF QSPI model.
5. **Two-phase emulation with `machine Reset`** instead of pre-staging slot 1 at power-on, so
   rejection evidence includes "v1 still runs after the staged update + reset".
6. **ccache** (`CCACHE_BASEDIR=/tmp`, `CCACHE_NOHASHDIR=1`, fixed key path) warmed at image build.

## Measured (local, Docker Desktop/WSL2, 8 vCPU)

Full run of the 7 templates: **~65 s** (D01 incl. sysbuild 18.5 s, E01 7.4 s, E08 12.3 s,
E03 13.1 s, E02 0.4 s, X01 12.4 s). Pages erased through the NVMC model (`nvmc PageErases`):
E01 0, E08 17 (swap-move), E03/X01 118 (MCUboot erases the whole rejected slot 1). UART excerpts:

```
E01  I: Jumping to the first image slot
     RP-APP version=1.0.0 build=0 key=30b8e43aa941036e slot=0xc000
E08  I: Image index: 0, Swap type: test / I: Starting swap using move algorithm.
     RP-APP version=2.0.0 build=0 key=30b8e43aa941036e slot=0xc000
E03  E: Image in the secondary slot is not valid!
     RP-APP version=1.0.0 build=0 key=30b8e43aa941036e slot=0xc000
X01  E: Image in the secondary slot is not valid!   (v1 keeps running)
E02  Error: Invalid value for '-t' / '--type': 'ml-dsa-65' is not one of 'rsa-2048', 'rsa-3072',
     'ecdsa-p256', 'ecdsa-p384', 'ed25519', 'x25519'.
```

## Known limitations

- The NVMC model does not enforce write-enable, 1→0-only programming, timing or UICR erase;
  no CryptoCell (MCUboot uses software tinycrypt ECDSA). Not a power-fail/interrupted-swap model
  (E12 stays UNKNOWN).
- E08 observes the *test* swap (v2 runs after the first reset); the revert/confirm cycle is not
  exercised.
- The staged image is written by the Renode monitor (`LoadBinary`), not by an in-app DFU client.
- E11 is a static decision on partitions/Kconfig of this build: it detects the absence of a
  bootloader-update path in upstream single-stage MCUboot; it does not prove the absence of
  out-of-band (debug-probe/depot) reflashing.
- E05 `layout_fit.boot_slot_capacity` is the slot-0 partition size; MCUboot swap-move additionally
  reserves one sector + trailer.
- `observed_version` is the major version (1 or 2), consistent with the wolfBoot integer.
- Image is x86_64 only (linux/amd64).
