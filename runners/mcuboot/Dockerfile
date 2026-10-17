# syntax=docker/dockerfile:1.6
# ReleaseProof MCUboot runner.
# Build context = repository root:
#   docker build -f runners/mcuboot/Dockerfile -t releaseproof/runner-mcuboot:0.1.0 .
# Every source is fetched here at a pinned version; a job needs no network.

FROM ubuntu:24.04 AS base
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git cmake ninja-build device-tree-compiler ccache \
        python3 python3-venv python3-pip xz-utils wget file make libicu74 \
    && rm -rf /var/lib/apt/lists/*

# Renode 1.16.1
ARG RENODE_VERSION=1.16.1
ARG RENODE_SHA256=00e113cdbd0f5354cf2f64bbe3f5a070d8958409542fca66e45ac97d982938c0
RUN wget -q -O /tmp/renode.tgz \
        https://github.com/renode/renode/releases/download/v${RENODE_VERSION}/renode-${RENODE_VERSION}.linux-portable-dotnet.tar.gz \
    && echo "${RENODE_SHA256}  /tmp/renode.tgz" | sha256sum -c - \
    && mkdir -p /opt/renode && tar -xzf /tmp/renode.tgz -C /opt/renode --strip-components=1 \
    && rm /tmp/renode.tgz && ln -s /opt/renode/renode /usr/local/bin/renode \
    && mkdir -p /opt/rp/renode-assets \
    && wget -q -O /opt/rp/renode-assets/NRF52840.svd.gz https://dl.antmicro.com/projects/renode/svd/NRF52840.svd.gz \
    && sha256sum /opt/rp/renode-assets/NRF52840.svd.gz > /opt/rp/renode-assets/NRF52840.svd.gz.sha256

# Zephyr SDK 0.17.4 (Arm only)
ARG SDK_VERSION=0.17.4
ARG SDK_MIN_SHA256=a7258bf50c892c4669712b2aacdfcd5e303245bcf36cb458a296039a664594f5
ARG SDK_ARM_SHA256=1b61084fe12076a3639aa2d028b5258f41eb3d0f7d46a16264949e1d213f1915
RUN cd /tmp \
    && wget -q https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v${SDK_VERSION}/zephyr-sdk-${SDK_VERSION}_linux-x86_64_minimal.tar.xz \
    && echo "${SDK_MIN_SHA256}  zephyr-sdk-${SDK_VERSION}_linux-x86_64_minimal.tar.xz" | sha256sum -c - \
    && tar -xJf zephyr-sdk-${SDK_VERSION}_linux-x86_64_minimal.tar.xz -C /opt \
    && wget -q https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v${SDK_VERSION}/toolchain_linux-x86_64_arm-zephyr-eabi.tar.xz \
    && echo "${SDK_ARM_SHA256}  toolchain_linux-x86_64_arm-zephyr-eabi.tar.xz" | sha256sum -c - \
    && tar -xJf toolchain_linux-x86_64_arm-zephyr-eabi.tar.xz -C /opt/zephyr-sdk-${SDK_VERSION} \
    && rm -f /tmp/*.tar.xz \
    && rm -rf /opt/zephyr-sdk-${SDK_VERSION}/hosttools* \
    && /opt/zephyr-sdk-${SDK_VERSION}/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc --version | head -1

# Python environment and west workspace
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
RUN python3 -m venv /opt/venv && pip install --no-cache-dir west==1.4.0

ARG ZEPHYR_VERSION=v4.2.0
WORKDIR /opt/zws
RUN git clone --depth 1 --branch ${ZEPHYR_VERSION} https://github.com/zephyrproject-rtos/zephyr /opt/zws/zephyr \
    && west init -l /opt/zws/zephyr \
    && west config manifest.project-filter -- "-.*,+cmsis,+cmsis_6,+hal_nordic,+mcuboot,+zcbor,+mbedtls,+tinycrypt" \
    && west update --narrow -o=--depth=1 \
    && west manifest --freeze --active-only > /opt/zws/manifest.freeze.yml \
    && west list -f "{name} {revision} {sha}" > /opt/zws/west-list.txt \
    && cat /opt/zws/west-list.txt \
    && pip install --no-cache-dir -r /opt/zws/zephyr/scripts/requirements-base.txt \
    && pip install --no-cache-dir -r /opt/zws/bootloader/mcuboot/scripts/requirements.txt \
    && pip freeze > /opt/zws/pip-freeze.txt

ENV ZEPHYR_BASE=/opt/zws/zephyr \
    ZEPHYR_SDK_INSTALL_DIR=/opt/zephyr-sdk-0.17.4 \
    ZEPHYR_TOOLCHAIN_VARIANT=zephyr \
    CCACHE_DIR=/opt/ccache \
    CCACHE_NOHASHDIR=1 \
    CCACHE_MAXSIZE=2G \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ReleaseProof runner
FROM base AS runner
COPY runners/common /opt/rp/common
COPY runners/mcuboot /opt/rp/mcuboot
ENV PYTHONPATH=/opt/rp/common:/opt/rp/mcuboot \
    RP_MCUBOOT_HOME=/opt/rp/mcuboot \
    RELEASEPROOF_DATA_DIR=/data \
    RUNNER_PORT=8080 \
    CCACHE_BASEDIR=/tmp
RUN useradd --uid 10001 --user-group --create-home --shell /usr/sbin/nologin rp \
 && mkdir -p /data/runs /opt/ccache /home/rp/.cache \
 && chown -R rp:rp /opt/ccache \
 && chown rp:rp /data/runs /home/rp/.cache \
 && git config --system --add safe.directory /opt/zws/zephyr \
 && git config --system --add safe.directory /opt/zws/bootloader/mcuboot \
 && cd /opt/zws && west config --local zephyr.base zephyr
ENV HOME=/home/rp XDG_CACHE_HOME=/home/rp/.cache
USER rp
# Warm and self-test the complete pipeline as the actual non-root runtime user.
# Zephyr must use this user's cache, not a root-owned cache under the source checkout.
RUN python -m rp_mcuboot.warm
EXPOSE 8080
WORKDIR /opt/rp
CMD ["python", "-m", "rp_mcuboot"]
