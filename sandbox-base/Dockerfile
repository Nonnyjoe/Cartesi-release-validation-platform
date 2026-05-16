# ─────────────────────────────────────────────────────────────
#  cartesi-rvp-sandbox:base
#  Pre-built image for each ephemeral test sandbox.
#  Contains: Docker CLI (DinD via socket mount), Anvil (Foundry),
#            Cartesi CLI (npm), Python test deps.
# ─────────────────────────────────────────────────────────────
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    FOUNDRY_DIR=/root/.foundry \
    PATH="/root/.foundry/bin:${PATH}"

# ── System deps ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    lsb-release \
    python3 \
    python3-pip \
    jq \
    netcat \
    docker.io \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# ── Foundry (includes Anvil, Cast, Forge) ─────────────────────
RUN curl -L https://foundry.paradigm.xyz | bash \
    && /root/.foundry/bin/foundryup

# ── Cartesi CLI ───────────────────────────────────────────────
# The CLI is NOT baked into this image. The provisioner builds a
# per-release cartesi-rvp-cli:<cli_version> image on-demand and starts
# it as a cli-tools sidecar in each sandbox's Docker network.
# For local debugging, install manually: npm install -g @cartesi/cli@<ver>

# ── Python test dependencies ──────────────────────────────────
COPY requirements.txt /tmp/sandbox-requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/sandbox-requirements.txt

# ── Setup script ──────────────────────────────────────────────
COPY setup.sh /usr/local/bin/setup-sandbox.sh
RUN chmod +x /usr/local/bin/setup-sandbox.sh

WORKDIR /sandbox

# Default: keep container alive; orchestrated by sandbox-manager
CMD ["tail", "-f", "/dev/null"]
