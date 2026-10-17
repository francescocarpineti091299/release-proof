# ReleaseProof wolfBoot runner (linux/amd64).
# Build from the repository root:
#   docker build -f runners/wolfboot/Dockerfile -t releaseproof/runner-wolfboot:0.1.0 .
# All sources and tools are fetched at image build time; the runner needs no network at job time.
FROM antmicro/renode:1.16.1

USER root
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils git make gcc libc6-dev python3 \
 && rm -rf /var/lib/apt/lists/*

# Arm GNU Toolchain 14.2.rel1 (x86_64 host, arm-none-eabi), verified against Arm's published sha256.
ARG ARM_TC_VERSION=14.2.rel1
ARG ARM_TC_NAME=arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi
RUN set -eu; \
    base="https://developer.arm.com/-/media/Files/downloads/gnu/${ARM_TC_VERSION}/binrel"; \
    cd /tmp; \
    curl -fsSL --retry 3 -o tc.tar.xz "${base}/${ARM_TC_NAME}.tar.xz"; \
    curl -fsSL --retry 3 -o tc.sha256asc "${base}/${ARM_TC_NAME}.tar.xz.sha256asc"; \
    echo "$(cut -d' ' -f1 tc.sha256asc)  tc.tar.xz" | sha256sum -c -; \
    mkdir -p /opt/arm-gnu-toolchain; \
    tar -xJf tc.tar.xz -C /opt/arm-gnu-toolchain --strip-components=1; \
    cp tc.sha256asc /opt/arm-gnu-toolchain/SHA256SUM; \
    rm -f tc.tar.xz tc.sha256asc; \
    rm -rf /opt/arm-gnu-toolchain/share/doc /opt/arm-gnu-toolchain/share/info /opt/arm-gnu-toolchain/share/man
ENV PATH=/opt/arm-gnu-toolchain/bin:${PATH}

# wolfBoot at the pinned commit + lib/wolfssl at the gitlink recorded by that commit.
ARG WOLFBOOT_REPO=https://github.com/wolfSSL/wolfBoot
ARG WOLFBOOT_COMMIT=4c79eee999b7083743811f37928322fe78b9fdb1
ARG WOLFSSL_REPO=https://github.com/wolfSSL/wolfssl.git
ARG WOLFSSL_COMMIT=4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f
RUN set -eu; \
    git config --global advice.detachedHead false; \
    git config --global core.autocrlf false; \
    git init -q /opt/wolfboot; \
    cd /opt/wolfboot; \
    git remote add origin "${WOLFBOOT_REPO}"; \
    git fetch -q --depth 1 origin "${WOLFBOOT_COMMIT}"; \
    git checkout -q --detach FETCH_HEAD; \
    test "$(git rev-parse HEAD)" = "${WOLFBOOT_COMMIT}"; \
    test "$(git ls-tree HEAD lib/wolfssl | awk '{print $3}')" = "${WOLFSSL_COMMIT}"; \
    rm -rf lib/wolfssl; \
    git init -q lib/wolfssl; \
    git -C lib/wolfssl remote add origin "${WOLFSSL_REPO}"; \
    git -C lib/wolfssl fetch -q --depth 1 origin "${WOLFSSL_COMMIT}"; \
    git -C lib/wolfssl checkout -q --detach FETCH_HEAD; \
    test "$(git -C lib/wolfssl rev-parse HEAD)" = "${WOLFSSL_COMMIT}"

# Pre-build the host key tools (keygen/sign) once; per-run copies reuse them (make keytools is a no-op).
RUN set -eu; \
    cd /opt/wolfboot; \
    make -C tools/keytools -j"$(nproc)" >/opt/keytools-build.log 2>&1 || (tail -n 60 /opt/keytools-build.log; exit 1); \
    test -x tools/keytools/sign; test -x tools/keytools/keygen; \
    git status --porcelain --ignored > /opt/wolfboot-baked-status.txt; \
    chmod -R a-w /opt/wolfboot

COPY runners/common/rp_runner /opt/releaseproof/rp_runner
COPY runners/wolfboot/rp_wolfboot /opt/releaseproof/rp_wolfboot

ENV PYTHONPATH=/opt/releaseproof \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RELEASEPROOF_DATA_DIR=/data \
    RUNNER_PORT=8080 \
    WOLFBOOT_BAKED_TREE=/opt/wolfboot \
    ARM_TOOLCHAIN_RELEASE=14.2.rel1

# Root keeps the shared /data volume writable regardless of the volume owner.
WORKDIR /opt/releaseproof
EXPOSE 8080
ENTRYPOINT ["python3", "-m", "rp_wolfboot"]
