# ─────────────────────────────────────────────────────────────
#  rvp-cannon-deployer
#  One-shot container that deploys Cartesi rollups contracts
#  into a running Anvil instance using Cannon, then prints the
#  deployed addresses as JSON to stdout.
#
#  Required env vars (injected by sandbox-manager provisioner):
#    CONTRACTS_VERSION  e.g. "2.2.0"
#    ANVIL_URL          e.g. "http://rvp-anvil-abcd1234:8545"
#    DEPLOYER_KEY       Anvil account #0 private key
# ─────────────────────────────────────────────────────────────

# Stage 1: grab Foundry binaries (statically linked Rust — works across distros)
FROM ghcr.io/foundry-rs/foundry:latest AS foundry

# Stage 2: Node runtime + Cannon CLI + Foundry binaries
FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tar \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Foundry binaries from the foundry stage (forge is required by cannon build)
COPY --from=foundry /usr/local/bin/forge  /usr/local/bin/forge
COPY --from=foundry /usr/local/bin/cast   /usr/local/bin/cast
COPY --from=foundry /usr/local/bin/anvil  /usr/local/bin/anvil

# Install Cannon CLI globally
RUN npm install -g @usecannon/cli --quiet

COPY deploy-contracts.sh /usr/local/bin/deploy-contracts.sh
RUN chmod +x /usr/local/bin/deploy-contracts.sh

ENTRYPOINT ["/usr/local/bin/deploy-contracts.sh"]
