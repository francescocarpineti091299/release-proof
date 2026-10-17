# Runner safety model

Shared rules that every runner (`rp_runner`) follows when reporting execution and evidence.

## Corrected evidence boundaries

- An execution with `ERROR` or deadline/cancellation `NOT_EXECUTED` finishes
  `FAILED`. A functional test result `FAIL` still represents a successfully
  executed test, not an infrastructure failure.
- wolfBoot requires an application version frame to establish an applied update.
  `Booting version` is printed before verification and cannot establish success.
  Contradictory version frames or a frame plus boot panic remain `UNKNOWN`.
- A failed/timed-out emulator cannot produce a passing result from partial UART.
  MCUboot clears old UART/backend logs before starting a scenario.
- wolfBoot's classical-image negative control requires both header-mismatched
  and header-matched cells to reject; an unexecuted header-matched control is not
  proof of a PQC-only signature policy.
- Literal Make parsers respect `?=` and `+=`; short image prefixes and truncated
  TLVs fail explicitly instead of being partially interpreted.

## Processes and HTTP

`run_cmd` rejects invalid timeout/streaming options, kills POSIX descendants even
when the group leader has exited, synchronizes its timeout worker, and reaps the
child on exception. Windows uses `taskkill /T /F` plus a parent-kill fallback.
Version commands with nonzero exit codes are unavailable, not successful probes.

`POST /execute` validates JSON types, unique registered templates, timeout range,
safe run identifiers and the exact `data/runs/<run_id>/artifacts` destination.
Symlink redirects and nonempty evidence directories are rejected. Bodies are
limited to 1 MiB with a 30-second read timeout; unsupported transfer encodings
and invalid framing receive HTTP 400 before any event stream begins.

This is **not an authenticated multi-tenant service**. Keep the runner on a trusted
internal network. Path checks do not protect against an attacker concurrently
modifying the shared data volume (filesystem TOCTOU). Windows process cleanup
cannot reliably address a detached descendant after its parent has already exited;
POSIX groups also do not contain processes which deliberately detach themselves.

## Offline tests

From the repository root, PowerShell:

```powershell
$env:PYTHONPATH='runners\common;runners\wolfboot;runners\mcuboot'
python -m unittest discover -s runners/common/tests -v
python -m unittest discover -s runners/wolfboot/tests -v
python -m unittest discover -s runners/mcuboot/tests -v
```

Verified on Python 3.13 / Windows: 25 passing tests, 2 platform-specific skips.
Verified on Python 3.12 / Linux Docker with read-only source mounts and networking
disabled: all 27 tests pass, including symlink redirection and the TERM-resistant
descendant holding the output pipe open. HTTP tests use a real local HTTP server
with an explicitly offline family, not the firmware toolchain.

Full firmware builds/Renode smoke runs were not executed. Existing runner images
were found, but their presence is not evidence that these modified sources build
or emulate successfully. UART parsing remains an observation of the configured
fixture, not cryptographic attestation of arbitrary untrusted firmware.
