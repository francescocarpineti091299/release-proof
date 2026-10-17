# Third-party notices

ReleaseProof's own code is MIT-licensed (see `LICENSE`). The following third-party components are
**used as tools at build/run time** inside container images. They are not included in this
repository. Their licenses apply to those images.

| Component | Pin | License | How it is used |
|---|---|---|---|
| wolfBoot | `4c79eee999b7083743811f37928322fe78b9fdb1` | GPL-3.0 (commercial license available from wolfSSL) | Cloned in `runner-wolfboot` image; built and executed in emulation. Not linked into ReleaseProof. |
| wolfSSL / wolfCrypt | `4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f` | GPL-3.0 (commercial available) | wolfBoot submodule, same as above. |
| Renode | 1.16.1 | MIT | Emulator in both runner images. |
| Zephyr RTOS | v4.2.0 | Apache-2.0 | Cloned in `runner-mcuboot` image via west. |
| MCUboot (+ imgtool) | Zephyr v4.2.0 manifest revision | Apache-2.0 | Bootloader and signing tool in `runner-mcuboot`. |
| Zephyr SDK | 0.17.4 | Various (GPL toolchain components) | Compiler toolchain in `runner-mcuboot`. |
| Arm GNU Toolchain | 14.2.rel1 | GPL-3.0 with runtime exceptions | Compiler in `runner-wolfboot`. |
| Python packages, Next.js/React | see `backend/pyproject.toml`, `web/package.json` | MIT / BSD / Apache-2.0 | Application dependencies. |

Exact application package versions and license metadata (including transitive dependencies)
are recorded in `docs/DEPENDENCY_INVENTORY.json`; see `DEPENDENCIES.md` for scope and reproduction.

If you publish runner images, you must also comply with the source-availability obligations of
the GPL components they contain.
