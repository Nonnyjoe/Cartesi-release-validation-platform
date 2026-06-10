# Cartesi Honeypot — Local Devnet Setup Guide

A complete, step-by-step guide to running the honeypot Rust dApp on a local devnet,
starting from nothing. Every command is literal and runnable. Sections that describe
known failure modes are cross-referenced inline.

---

## Contents

- [Prerequisites](#prerequisites)
- [Step 1 — Configure the environment file](#step-1--configure-the-environment-file)
- [Step 2 — Start the Docker stack](#step-2--start-the-docker-stack)
- [Step 3 — Deploy Cartesi rollups contracts](#step-3--deploy-cartesi-rollups-contracts)
- [Step 4 — Deploy the TestToken ERC-20](#step-4--deploy-the-testtoken-erc-20)
- [Step 5 — Bake addresses into the machine image](#step-5--bake-addresses-into-the-machine-image)
- [Step 6 — Register the application](#step-6--register-the-application)
- [Step 7 — Test end-to-end](#step-7--test-end-to-end)
- [Known Issues and Fixes](#known-issues-and-fixes)

---

## Prerequisites

The following tools must be installed before starting. Versions listed are what was
tested and confirmed working.

### Foundry (anvil, forge, cast)

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

Confirm:

```bash
anvil --version   # anvil 1.x
forge --version
cast --version
```

### Cannon CLI

```bash
npm install -g @usecannon/cli
cannon --version  # 2.26.0
```

### Cartesi CLI

```bash
npm install -g @cartesi/cli
cartesi --version
```

### Docker with Compose v2

```bash
docker --version
docker compose version  # must be v2 (uses `docker compose`, not `docker-compose`)
```

### jq

```bash
brew install jq          # macOS
# apt-get install -y jq  # Debian/Ubuntu
```

---

## Step 1 — Configure the environment file

All commands below assume you are in the `honeypot-rust/` directory unless stated
otherwise.

```bash
cd honeypot-rust
```

Copy the example file and open it for editing:

```bash
cp .env.example .env
```

The `.env` file is read by `compose.local.yaml` at startup. Set it to the following
values for a local Anvil devnet. The contract addresses listed here are the deterministic
CREATE2 addresses for `rollups-contracts v2.2.0` on chain-id 31337 — they are the same
on every fresh Anvil.

```dotenv
# Auth
AUTH_KIND=private_key
# Anvil account #0 private key — well-known devnet key, never use in production
CARTESI_AUTH_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

# Blockchain
BLOCKCHAIN_ID=31337

# rollups-contracts v2.2.0 — deterministic addresses, same on every fresh chain-id 31337
CARTESI_CONTRACTS_INPUT_BOX_ADDRESS=0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac
CARTESI_CONTRACTS_AUTHORITY_FACTORY_ADDRESS=0x5E96408CFE423b01dADeD3bc867E6013135990cc
CARTESI_CONTRACTS_APPLICATION_FACTORY_ADDRESS=0x26E758238CB6eC5aB70ce0dd52aF2d7b82e1972E
CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS=0x010D3CbB4223F5bCc7b7B03cEE59f3aAea8eDb8A

# Honeypot config
ERC20_PORTAL_ADDRESS=0xACA6586A0Cf05bD831f2501E7B4aea550dA6562D
# Anvil account #1 — receives withdrawn tokens
ERC20_WITHDRAWAL_ADDRESS=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
# Fill this in after Step 4 — the TestToken address changes on every fresh Anvil
ERC20_TOKEN_ADDRESS=
```

Leave `ERC20_TOKEN_ADDRESS` blank for now. It will be filled in after Step 4.

---

## Step 2 — Start the Docker stack

From `honeypot-rust/`:

```bash
docker compose -f compose.local.yaml up -d
```

This starts 7 containers: `anvil`, `database`, `evm-reader`, `advancer`, `validator`,
`claimer`, and `jsonrpc-api`. Check they are all running:

```bash
docker compose -f compose.local.yaml ps
```

Expected — all entries show `Up`:

```
NAME          STATUS
advancer      Up
anvil         Up (healthy)
claimer       Up
database      Up (healthy)
evm-reader    Up
jsonrpc-api   Up
validator     Up
```

> **If `evm-reader` or `claimer` are missing** (crashed and not restarted), see
> [Issue 1 — evm-reader crashes with "connection refused"](#issue-1--evm-reader-crashes-with-connection-refused)
> and [Issue 2 — evm-reader exits with "no new block header"](#issue-2--evm-reader-exits-with-no-new-block-header).

Confirm Anvil is producing blocks and reachable from the host:

```bash
cast block-number --rpc-url http://localhost:8545
# Should increment by 1 each second
```

Confirm Anvil is reachable from inside the Docker network (required by evm-reader):

```bash
docker exec evm-reader wget -qO- http://anvil:8545 2>&1 | head -1
# Should NOT return "connection refused"
```

> **If the stack was previously run on a different network** (e.g. Arbitrum Sepolia,
> chain-id 84532) the database will reject the new chain-id. See
> [Issue 3 — chain-id mismatch](#issue-3--chain-id-mismatch-in-evm-reader).

---

## Step 3 — Deploy Cartesi rollups contracts

The contracts are deployed once per fresh Anvil using the
[Cannon](https://usecannon.com) build system. The resulting addresses are deterministic
(CREATE2) and will always be the same on chain-id 31337 with the standard deployer key.

### 3a — Check if contracts are already deployed

If Anvil state was preserved (no restart, no `docker compose down -v`) the contracts
may already be live:

```bash
cast code 0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac --rpc-url http://localhost:8545
```

- Output is a long hex string → contracts are deployed, **skip to Step 4**.
- Output is `0x` → contracts are not deployed, continue below.

### 3b — Download rollups-contracts source

Run these commands from any directory — a temp directory is created automatically:

```bash
export CONTRACTS_VERSION="2.2.0"
export TMP=$(mktemp -d)

curl -fsSL --http1.1 --retry 3 --retry-delay 2 \
  "https://github.com/cartesi/rollups-contracts/archive/refs/tags/v${CONTRACTS_VERSION}.tar.gz" \
  -o "${TMP}/src.tar.gz"

tar -xzf "${TMP}/src.tar.gz" -C "${TMP}"
```

> `--http1.1` is required. GitHub's CDN occasionally drops HTTP/2 connections
> mid-transfer (curl exits with code 18). HTTP/1.1 avoids this. See
> [Issue 9 — curl HTTP/2 partial transfer](#issue-9--curl-http2-partial-transfer).

### 3c — Install Solidity dependencies

```bash
cd "${TMP}/rollups-contracts-${CONTRACTS_VERSION}"
forge soldeer install
# Takes ~30–60 seconds on first run
```

### 3d — Build and deploy with Cannon

```bash
cannon build cannonfile.toml \
  --rpc-url http://localhost:8545 \
  --chain-id 31337 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --wipe
```

`--wipe` clears any cached Cannon state for this package+chain, ensuring a clean
deployment even if a previous run left partial state. Takes 2–4 minutes.

Expected output tail:

```
✔  ApplicationFactory deployed at 0x26E758238CB6eC5aB70ce0dd52aF2d7b82e1972E
✔  AuthorityFactory    deployed at 0x5E96408CFE423b01dADeD3bc867E6013135990cc
✔  InputBox            deployed at 0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac
✔  SelfHostedApplicationFactory deployed at 0x010D3CbB4223F5bCc7b7B03cEE59f3aAea8eDb8A
💥 cartesi-rollups:2.2.0@main built on Anvil (Chain ID: 31337)
```

### 3e — Verify

```bash
cast code 0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac --rpc-url http://localhost:8545 | wc -c
# Should be > 10 (non-empty bytecode)
```

---

## Step 4 — Deploy the TestToken ERC-20

The honeypot requires an ERC-20 token contract. This is a standard `CREATE` deployment
(not CREATE2), so its address changes on every fresh Anvil and must be recorded each time.

> **Why not `forge create`?** Foundry 1.5+ changed `forge create` to show a dry-run
> preview and require an interactive `[y/N]` confirmation before broadcasting. That
> prompt cannot be scripted. See
> [Issue 6 — forge create does not broadcast](#issue-6--forge-create-does-not-broadcast).
> Use `cast send --create` instead — it broadcasts immediately.

### 4a — Deploy

Run this from any directory. The bytecode below is `SimpleERC20` (OpenZeppelin ERC-20
5.2.0) compiled from `rollups-contracts v2.2.0`, with constructor args pre-encoded for
minter = Anvil account #1 (`0x70997970...`) and initial supply = 1,000,000 tokens
(18 decimals):

```bash
cast send \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --create 0x6080604052346103b1576109e26040813803918261001c816103b5565b9384928339810103126103b15780516001600160a01b03811691908290036103b1576020015161004c60406103b5565b91600b83526a053696d706c6545524332360ac1b602084015261006f60406103b5565b6005815264053494d32360dc1b602082015283519092906001600160401b0381116102c257600354600181811c911680156103a7575b60208210146102a457601f8111610344575b50602094601f82116001146102e1579481929394955f926102d6575b50508160011b915f199060031b1c1916176003555b82516001600160401b0381116102c257600454600181811c911680156102b8575b60208210146102a457601f8111610241575b506020601f82116001146101de57819293945f926101d3575b50508160011b915f199060031b1c1916176004555b81156101c057600254908082018092116101ac5760207fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef915f9360025584845283825260408420818154019055604051908152a360405161060790816103db8239f35b634e487b7160e01b5f52601160045260245ffd5b63ec442f0560e01b5f525f60045260245ffd5b015190505f80610134565b601f1982169060045f52805f20915f5b81811061022957509583600195969710610211575b505050811b01600455610149565b01515f1960f88460031b161c191690555f8080610203565b9192602060018192868b0151815501940192016101ee565b60045f527f8a35acfbc15ff81a39ae7d344fd709f28e8600b4aa8c65c6b64bfe7fe36bd19b601f830160051c8101916020841061029a575b601f0160051c01905b81811061028f575061011b565b5f8155600101610282565b9091508190610279565b634e487b7160e01b5f52602260045260245ffd5b90607f1690610109565b634e487b7160e01b5f52604160045260245ffd5b015190505f806100d3565b601f1982169560035f52805f20915f5b88811061032c57508360019596979810610314575b505050811b016003556100e8565b01515f1960f88460031b161c191690555f8080610306565b919260206001819286850151815501940192016102f1565b60035f527fc2575a0e9e593c00f959f8c92f12db2869c3395a3b0502d05e2516446f71f85b601f830160051c8101916020841061039d575b601f0160051c01905b81811061039257506100b7565b5f8155600101610385565b909150819061037c565b90607f16906100a5565b5f80fd5b6040519190601f01601f191682016001600160401b038111838210176102c25760405256fe6080806040526004361015610012575f80fd5b5f3560e01c90816306fdde03146103ef57508063095ea7b31461036d57806318160ddd1461035057806323b872dd14610271578063313ce5671461025657806370a082311461021f57806395d89b4114610104578063a9059cbb146100d35763dd62ed3e1461007f575f80fd5b346100cf5760403660031901126100cf576100986104e8565b6100a06104fe565b6001600160a01b039182165f908152600160209081526040808320949093168252928352819020549051908152f35b5f80fd5b346100cf5760403660031901126100cf576100f96100ef6104e8565b6024359033610514565b602060405160018152f35b346100cf575f3660031901126100cf576040515f6004548060011c90600181168015610215575b602083108114610201578285529081156101e55750600114610190575b50819003601f01601f191681019067ffffffffffffffff82118183101761017c57610178829182604052826104be565b0390f35b634e487b7160e01b5f52604160045260245ffd5b905060045f527f8a35acfbc15ff81a39ae7d344fd709f28e8600b4aa8c65c6b64bfe7fe36bd19b5f905b8282106101cf57506020915082010182610148565b60018160209254838588010152019101906101ba565b90506020925060ff191682840152151560051b82010182610148565b634e487b7160e01b5f52602260045260245ffd5b91607f169161012b565b346100cf5760203660031901126100cf576001600160a01b036102406104e8565b165f525f602052602060405f2054604051908152f35b346100cf575f3660031901126100cf57602060405160128152f35b346100cf5760603660031901126100cf5761028a6104e8565b6102926104fe565b6001600160a01b0382165f818152600160209081526040808320338452909152902054909260443592915f1981106102d0575b506100f99350610514565b83811061033557841561032257331561030f576100f9945f52600160205260405f2060018060a01b0333165f526020528360405f2091039055846102c5565b634a1406b160e11b5f525f60045260245ffd5b63e602df0560e01b5f525f60045260245ffd5b8390637dc7a0d960e11b5f523360045260245260445260645ffd5b346100cf575f3660031901126100cf576020600254604051908152f35b346100cf5760403660031901126100cf576103866104e8565b602435903315610322576001600160a01b031690811561030f57335f52600160205260405f20825f526020528060405f20556040519081527f8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b92560203392a3602060405160018152f35b346100cf575f3660031901126100cf575f6003548060011c906001811680156104b4575b602083108114610201578285529081156101e5575060011461045f5750819003601f01601f191681019067ffffffffffffffff82118183101761017c57610178829182604052826104be565b905060035f527fc2575a0e9e593c00f959f8c92f12db2869c3395a3b0502d05e2516446f71f85b5f905b82821061049e57506020915082010182610148565b6001816020925483858801015201910190610489565b91607f1691610413565b602060409281835280519182918282860152018484015e5f828201840152601f01601f1916010190565b600435906001600160a01b03821682036100cf57565b602435906001600160a01b03821682036100cf57565b6001600160a01b03169081156105be576001600160a01b03169182156105ab57815f525f60205260405f205481811061059257817fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef92602092855f525f84520360405f2055845f525f825260405f20818154019055604051908152a3565b8263391434e360e21b5f5260045260245260445260645ffd5b63ec442f0560e01b5f525f60045260245ffd5b634b637e8f60e11b5f525f60045260245ffdfea2646970667358221220cac874b0e5b3f14a7f7e4b7e5415a81424893ae66b4ef42c436a3ec4b502262a64736f6c634300081e003300000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c800000000000000000000000000000000000000000000d3c21bcecceda1000000
```

### 4b — Record the token address

The transaction receipt contains a `contractAddress` field:

```
contractAddress      0x<your_new_token_address>
status               1 (success)
```

Save it:

```bash
export TOKEN=<paste_contractAddress_here>
```

### 4c — Verify the token was deployed

```bash
cast call $TOKEN "balanceOf(address)(uint256)" \
  0x70997970C51812dc3A010C7d01b50e0d17dc79C8 \
  --rpc-url http://localhost:8545
# Expected: 1000000000000000000000000
```

### 4d — Update .env

In `honeypot-rust/.env`, fill in the token address recorded above:

```
ERC20_TOKEN_ADDRESS=<paste_contractAddress_here>
```

---

## Step 5 — Bake addresses into the machine image

> **This step is critical.** The Cartesi machine image is a RISC-V snapshot produced by
> `cartesi build`. `ENV` variables in the `Dockerfile` are embedded into that snapshot at
> build time. Docker Compose environment variables, `.env` entries, and `docker run -e`
> flags have **no effect** on code running inside the Cartesi VM. The dApp reads
> `ERC20_TOKEN_ADDRESS` from the baked ENV, not from the host. See
> [Issue 5 — machine ENV vars not updated at runtime](#issue-5--machine-env-vars-not-updated-at-runtime).

### 5a — Edit the Dockerfile

In `honeypot-rust/Dockerfile`, find the three `ENV` lines near the bottom (around
line 116–120) and set the correct addresses:

```dockerfile
# Before:
ENV ERC20_PORTAL_ADDRESS="0xACA6586A0Cf05bD831f2501E7B4aea550dA6562D"
ENV ERC20_WITHDRAWAL_ADDRESS="0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
ENV ERC20_TOKEN_ADDRESS="<old_or_placeholder>"

# After — paste the contractAddress from Step 4:
ENV ERC20_PORTAL_ADDRESS="0xACA6586A0Cf05bD831f2501E7B4aea550dA6562D"
ENV ERC20_WITHDRAWAL_ADDRESS="0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
ENV ERC20_TOKEN_ADDRESS="<your_token_address_from_step_4>"
```

The portal and withdrawal addresses are fixed for rollups-contracts v2.2.0 on chain-id
31337. Only `ERC20_TOKEN_ADDRESS` changes between deployments.

### 5b — Build the machine image

From `honeypot-rust/`:

```bash
cartesi build
```

This cross-compiles the Rust binary for `riscv64gc-unknown-linux-gnu`, installs it into
an Ubuntu Noble RISC-V image together with `machine-guest-tools`, and runs it once inside
the Cartesi machine to produce the snapshot in `.cartesi/image/`.

Takes several minutes on first run (downloads the RISC-V Ubuntu base and Rust toolchain).
Subsequent builds are faster.

Confirm the dApp started with the correct addresses — look for these lines in the output:

```
[dapp] portal:     0xaca6586a0cf05bd831f2501e7b4aea550da6562d
[dapp] withdrawal: 0x70997970c51812dc3a010c7d01b50e0d17dc79c8
[dapp] token:      0x<your_token_address>
[dapp] processing rollup requests...

Storing machine: please wait
```

If `token:` shows the wrong address, the Dockerfile `ENV` line was not updated correctly.
Fix it and re-run `cartesi build`.

### 5c — Restart the advancer

The `advancer` container has `.cartesi/image/` bind-mounted at
`/var/lib/cartesi-rollups-node/snapshot/`. After `cartesi build` recreates that
directory the container must be restarted to pick up the new snapshot:

```bash
# From honeypot-rust/
docker compose -f compose.local.yaml restart advancer
```

> **If the advancer logs show `"unable to open '.../config.json' for reading"`** after
> restart, the snapshot path used at registration time is wrong. See
> [Issue 4 — advancer cannot find config.json](#issue-4--advancer-cannot-find-configjson).

Confirm the advancer loaded the machine successfully:

```bash
docker compose -f compose.local.yaml logs advancer --tail=10
# Good: "Loading machine runtime from template ... path=/var/lib/cartesi-rollups-node/snapshot"
# Bad:  "Failed to create machine instance ... unable to open '/xxx/config.json'"
```

---

## Step 6 — Register the application

`cartesi-rollups-cli` is the tool that deploys the application and authority contracts
on-chain and registers the application in the node's database. It lives inside the
`cartesi/rollups-runtime` Docker image, so it runs as a one-shot container on the same
Docker network as the stack.

> **Note on the Docker network name.** Docker Compose derives the network name from the
> `name:` field at the top of `compose.local.yaml`. That field is set to
> `cartesi-rollups-node`, so the network is `cartesi-rollups-node_default`. If you ever
> change the `name:` field, update the `--network` flag accordingly.

> **Note on the template path.** The second positional argument to
> `deploy application` is the path the **advancer** uses to load the machine. Pass the
> path as it appears **inside the advancer container** — which is
> `/var/lib/cartesi-rollups-node/snapshot` — not a path inside the CLI container.
> Passing any other path causes the advancer to fail on every input. See
> [Issue 4 — advancer cannot find config.json](#issue-4--advancer-cannot-find-configjson).

From `honeypot-rust/`:

```bash
docker run --rm \
  --network cartesi-rollups-node_default \
  -v "$(pwd)/.cartesi/image:/snapshot" \
  -e CARTESI_AUTH_KIND=private_key \
  -e CARTESI_AUTH_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  -e CARTESI_BLOCKCHAIN_HTTP_ENDPOINT=http://anvil:8545 \
  -e CARTESI_CONTRACTS_INPUT_BOX_ADDRESS=0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac \
  -e CARTESI_CONTRACTS_APPLICATION_FACTORY_ADDRESS=0x26E758238CB6eC5aB70ce0dd52aF2d7b82e1972E \
  -e CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS=0x010D3CbB4223F5bCc7b7B03cEE59f3aAea8eDb8A \
  -e "CARTESI_DATABASE_CONNECTION=postgres://postgres:password@database:5432/rollupsdb?sslmode=disable" \
  cartesi/rollups-runtime:0.12.0-alpha.39 \
  cartesi-rollups-cli deploy application honeypot-rust \
    /var/lib/cartesi-rollups-node/snapshot \
  --verbose
```

Expected output:

```
selfhosted deployment:
    application owner:     0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
    factory address:       0x010D3CbB4223F5bCc7b7B03cEE59f3aAea8eDb8A
    template hash:         0x<hash>
checking factory address...success
deploying...success
    application address:   0x<app_address>
    authority address:     0x<authority_address>
registering...success
    application name:      honeypot-rust
    application path:      /var/lib/cartesi-rollups-node/snapshot
```

Save the application address — you'll need it for Step 7:

```bash
export APP=<application_address_from_output>
```

### Verify registration

```bash
docker run --rm \
  --network cartesi-rollups-node_default \
  -e "CARTESI_DATABASE_CONNECTION=postgres://postgres:password@database:5432/rollupsdb?sslmode=disable" \
  cartesi/rollups-runtime:0.12.0-alpha.39 \
  cartesi-rollups-cli app list
```

The application should appear with `"state": "ENABLED"`.

---

## Step 7 — Test end-to-end

Use the following variables throughout. Replace `APP` and `TOKEN` with the values from
earlier steps:

```bash
export APP=<application_address>
export TOKEN=<token_address>
export PORTAL=0xACA6586A0Cf05bD831f2501E7B4aea550dA6562D
export INPUTBOX=0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac
export DEPOSITOR=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
export AMOUNT=500000000000000000000   # 500 tokens, 18 decimals
export RPC=http://localhost:8545
```

### 7a — Approve the ERC20Portal to spend tokens

```bash
cast send --rpc-url $RPC --unlocked --from $DEPOSITOR \
  $TOKEN \
  "approve(address,uint256)" $PORTAL $AMOUNT
```

Verify:

```bash
cast call $TOKEN "allowance(address,address)(uint256)" $DEPOSITOR $PORTAL --rpc-url $RPC
# Expected: 500000000000000000000
```

### 7b — Deposit 500 tokens into the honeypot

```bash
cast send --rpc-url $RPC --unlocked --from $DEPOSITOR \
  $PORTAL \
  "depositERC20Tokens(address,address,uint256,bytes)" \
  $TOKEN $APP $AMOUNT 0x
```

Wait ~5 seconds for the evm-reader to pick up the event and the advancer to process the
input. Check the advancer processed it:

```bash
docker compose -f compose.local.yaml logs advancer --tail=8
```

Expected lines:

```
[dapp] processing ERC-20 deposit
[dapp] successful deposit
INF Processing input finished ... status=ACCEPTED outputs=0 reports=1
```

> **If the advancer logs show `"invalid deposit token address"`**, the `ERC20_TOKEN_ADDRESS`
> in the Dockerfile does not match the deployed `$TOKEN`. See
> [Issue 5 — machine ENV vars not updated at runtime](#issue-5--machine-env-vars-not-updated-at-runtime).
> Update the Dockerfile, re-run `cartesi build`, restart advancer, and re-register.

### 7c — Inspect the balance

The inspect endpoint is served by the `advancer` on port **10012** (not the jsonrpc-api
on 10011). The method is `POST /inspect/{app-name}`:

```bash
curl -s -X POST http://localhost:10012/inspect/honeypot-rust \
  -H "Content-Type: application/json" \
  -d '"balance"'
```

Expected response:

```json
{
  "status": "Accepted",
  "reports": [
    { "payload": "0x00000000000000000000000000000000000000000000001b1ae4d6e2ef500000" }
  ],
  "processed_input_count": 1
}
```

`0x1b1ae4d6e2ef500000` is 500 × 10^18 — 500 tokens in big-endian 32-byte hex.

### 7d — Trigger withdrawal

Withdrawal is triggered by sending an **empty input** (`0x`) from the configured
`ERC20_WITHDRAWAL_ADDRESS`. Inputs from any other address are rejected with
`"invalid advance request"`.

> If you send from the wrong address, see
> [Issue 8 — withdrawal rejected with "invalid advance request"](#issue-8--withdrawal-rejected-with-invalid-advance-request).

```bash
cast send --rpc-url $RPC --unlocked --from $DEPOSITOR \
  $INPUTBOX \
  "addInput(address,bytes)" $APP 0x
```

(`$DEPOSITOR` = `0x70997970...` which is the same as `ERC20_WITHDRAWAL_ADDRESS`)

Wait ~5 seconds, then check the advancer:

```bash
docker compose -f compose.local.yaml logs advancer --tail=8
```

Expected lines:

```
[dapp] processing withdrawal request
[dapp] voucher emitted (201 Created)
[dapp] successful withdrawal
INF Processing input finished ... status=ACCEPTED outputs=1 reports=1
```

### 7e — Confirm balance is zero

```bash
curl -s -X POST http://localhost:10012/inspect/honeypot-rust \
  -H "Content-Type: application/json" \
  -d '"balance"'
```

Expected payload: `0x0000000000000000000000000000000000000000000000000000000000000000`

### 7f — Verify the voucher was recorded

```bash
docker exec database psql -U postgres -d rollupsdb \
  -c "SELECT input_index, index, encode(raw_data, 'hex') as raw_data FROM output;"
```

The `raw_data` of the voucher decodes as:

| Bytes   | Content                                                          |
|---------|------------------------------------------------------------------|
| 0–3     | `237a816f` — Cartesi voucher type selector                       |
| 16–35   | TestToken contract address (where the transfer call goes)        |
| 36–39   | `a9059cbb` — `transfer(address,uint256)` selector                |
| 52–71   | Withdrawal address (`0x70997970...`) — transfer recipient        |
| 72–103  | Amount in big-endian (500 × 10^18)                               |

---

## Known Issues and Fixes

### Issue 1 — evm-reader crashes with "connection refused"

**Symptom:**

```
evm-reader | Error: dial tcp 172.18.0.x:8545: connect: connection refused
```

`docker compose ps` shows `evm-reader` and `claimer` absent.

**Root cause:**

The `ghcr.io/foundry-rs/foundry` image declares `ENTRYPOINT ["/bin/sh", "-c"]`. When
Docker Compose processes a `command:` string (e.g.
`command: anvil --host 0.0.0.0 --port 8545 ...`) it passes each word as a separate
exec argument: `/bin/sh -c anvil --host 0.0.0.0 ...`. With `/bin/sh -c`, only the
first word after `-c` is the script; the remaining words become `$0`, `$1`, etc. and
are **never passed to `anvil`**. Anvil therefore starts with zero arguments and defaults
to binding on `127.0.0.1:8545` — unreachable from other containers.

Confirm the bad bind:

```bash
docker exec anvil sh -c 'cat /proc/net/tcp | grep 2161'
# BAD:  0100007F:2161  (= 127.0.0.1:8545)
# GOOD: 00000000:2161  (= 0.0.0.0:8545)
```

**Fix — already applied in `compose.local.yaml`:**

```yaml
anvil:
  image: ghcr.io/foundry-rs/foundry:latest
  entrypoint: ["anvil"]          # overrides the /bin/sh -c wrapper
  command: ["--host", "0.0.0.0", "--port", "8545", "--block-time", "1", "--chain-id", "31337"]
```

Using `entrypoint: ["anvil"]` + exec-array `command:` bypasses the shell wrapper and
passes all arguments directly to the `anvil` binary. The `compose.local.yaml` in this
repo already contains this fix. If you see this error, confirm the file has not been
reverted to the shell-string form.

---

### Issue 2 — evm-reader exits with "no new block header"

**Symptom:**

```
evm-reader | Subscription error: no new block header received for 2m0s
evm-reader | Max consecutive failures reached. Exiting
```

**Root cause:**

The evm-reader subscribes to new block headers over WebSocket. If Anvil is running in
**instant-mine mode** (no `--block-time` flag), it only mines a block when a transaction
is submitted. With no activity, the WS subscription starves, and the evm-reader exits
after 5 consecutive 2-minute timeouts.

This was also triggered by a **stale host-level Anvil process** (from a previous
`cartesi run` session) that was already bound to port 8545 in instant-mine mode,
preventing the Dockerized Anvil with `--block-time 1` from binding the port.

**Fix:**

1. Kill any host-level Anvil processes:
   ```bash
   pkill -f "anvil" || true
   ```
2. Confirm nothing is using port 8545 on the host:
   ```bash
   lsof -i :8545
   ```
3. Ensure the `anvil` service in `compose.local.yaml` has `--block-time 1` in the
   command array (already set in this repo).
4. Restart the stack:
   ```bash
   docker compose -f compose.local.yaml up -d
   ```

---

### Issue 3 — chain-id mismatch in evm-reader

**Symptom:**

```
evm-reader | chain-id mismatch: expected 31337, got 84532
```

**Root cause:**

The `database` Docker volume stores the chain-id at first initialization. If the stack
was previously pointed at a different network (e.g. Arbitrum Sepolia = 84532), the
database rejects the new chain-id on startup.

**Fix:**

Wipe the named volume to reset all database state:

```bash
docker compose -f compose.local.yaml down -v   # -v removes named volumes
docker compose -f compose.local.yaml up -d
```

This destroys all registered applications and input history. Re-run Steps 3–6 after
bringing the stack back up.

---

### Issue 4 — advancer cannot find config.json

**Symptom:**

```
advancer | Failed to create machine instance ...
         | unable to open '/snapshot/config.json' for reading: No such file or directory
```

**Root cause:**

`cartesi-rollups-cli deploy application` takes the template path as a positional
argument and stores it verbatim in the database. The advancer then opens that path inside
its own filesystem. If the path passed at registration time (`/snapshot` — a path inside
the CLI container) is not the same as where the snapshot is mounted inside the advancer
(`/var/lib/cartesi-rollups-node/snapshot`), the advancer cannot find the machine.

**Fix A — use the correct path at registration (preferred):**

Always pass the advancer-container path, not the CLI-container path:

```bash
cartesi-rollups-cli deploy application honeypot-rust \
  /var/lib/cartesi-rollups-node/snapshot   # ← advancer's mount point
```

**Fix B — correct the database if already registered with the wrong path:**

```bash
docker exec database psql -U postgres -d rollupsdb \
  -c "UPDATE application
      SET template_uri = '/var/lib/cartesi-rollups-node/snapshot',
          state = 'ENABLED'
      WHERE name = 'honeypot-rust'
      RETURNING name, template_uri, state;"

docker compose -f compose.local.yaml restart advancer
```

---

### Issue 5 — machine ENV vars not updated at runtime

**Symptom:**

```
advancer | [dapp] invalid deposit token address
```

Deposits are rejected even though the ERC20Portal and the correct token are being used.

**Root cause:**

The Cartesi machine image is a static RISC-V snapshot. `ENV` lines in the Dockerfile are
written into the snapshot filesystem at `cartesi build` time. They cannot be changed
without rebuilding the image. Updating `.env` or `compose.local.yaml` environment
variables has no effect on the running dApp.

**Fix:**

1. Update the `ENV ERC20_TOKEN_ADDRESS` line in `Dockerfile` to the new address.
2. Run `cartesi build` from `honeypot-rust/`.
3. `docker compose -f compose.local.yaml restart advancer`

If you also deployed a new application on-chain (new `$APP` address), re-run Step 6 as
well (first remove the old registration — see below).

**Removing an existing registration before re-registering:**

```bash
# Disable first (required before removal)
docker run --rm \
  --network cartesi-rollups-node_default \
  -e "CARTESI_DATABASE_CONNECTION=postgres://postgres:password@database:5432/rollupsdb?sslmode=disable" \
  cartesi/rollups-runtime:0.12.0-alpha.39 \
  cartesi-rollups-cli app status honeypot-rust disabled

# Then update the template_uri directly (the interactive `app remove` prompt
# cannot be scripted — the DB update below is the practical alternative):
docker exec database psql -U postgres -d rollupsdb \
  -c "DELETE FROM application WHERE name = 'honeypot-rust';"
```

---

### Issue 6 — forge create does not broadcast

**Symptom:**

```
Warning: Dry run enabled, not broadcasting transaction
```

Adding `--broadcast` still shows the dry-run warning.

**Root cause:**

Foundry 1.5+ requires interactive `[y/N]` confirmation before `forge create` broadcasts.
The `--broadcast` flag is accepted but still waits for stdin confirmation, which cannot
be scripted in a non-interactive shell.

**Fix:**

Use `cast send --create <bytecode>` instead. It broadcasts immediately and returns the
full transaction receipt including `contractAddress`.

---

### Issue 7 — advancer loads stale machine after cartesi build

**Symptom:**

After running `cartesi build`, the advancer still logs the old machine hash.

**Root cause:**

`cartesi build` deletes and recreates `.cartesi/image/`. When a Docker bind mount's
source directory is removed and recreated on the host, the container may hold a reference
to the old inode and not see the new contents.

**Fix:**

Always restart the advancer after `cartesi build`:

```bash
docker compose -f compose.local.yaml restart advancer
```

---

### Issue 8 — withdrawal rejected with "invalid advance request"

**Symptom:**

```
advancer | [dapp] invalid advance request from 0xf39fd6e5...
```

The balance does not change after sending an empty input.

**Root cause:**

The honeypot's withdrawal handler in `src/main.rs` (line ~317) requires two conditions:

```rust
if address_eq(msg_sender, &config.withdrawal_address) && payload_bytes.is_empty() {
```

Both must be true: the input must come from `ERC20_WITHDRAWAL_ADDRESS` **and** the
payload must be empty. Any other sender is rejected.

**Fix:**

Send the withdrawal input from `ERC20_WITHDRAWAL_ADDRESS` (Anvil account #1):

```bash
cast send --rpc-url http://localhost:8545 \
  --unlocked --from 0x70997970C51812dc3A010C7d01b50e0d17dc79C8 \
  0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac \
  "addInput(address,bytes)" $APP 0x
```

---

### Issue 9 — curl HTTP/2 partial transfer

**Symptom:**

```
curl: (18) HTTP/2 stream 1 was not closed cleanly before end of the underlying stream
```

The rollups-contracts tarball download fails.

**Root cause:**

GitHub's CDN occasionally drops HTTP/2 connections mid-transfer.

**Fix:**

The `--http1.1` flag in the download command (Step 3b) prevents this.
`--retry 3 --retry-delay 2` handles any remaining transient failures.

---

## Addresses quick-reference

### rollups-contracts v2.2.0 — deterministic on chain-id 31337

| Contract                      | Address                                      |
|-------------------------------|----------------------------------------------|
| InputBox                      | `0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac` |
| AuthorityFactory              | `0x5E96408CFE423b01dADeD3bc867E6013135990cc` |
| ApplicationFactory            | `0x26E758238CB6eC5aB70ce0dd52aF2d7b82e1972E` |
| SelfHostedApplicationFactory  | `0x010D3CbB4223F5bCc7b7B03cEE59f3aAea8eDb8A` |
| ERC20Portal                   | `0xACA6586A0Cf05bD831f2501E7B4aea550dA6562D` |

### Anvil default accounts (devnet only — never use in production)

| # | Address                                      | Private Key                                                          |
|---|----------------------------------------------|----------------------------------------------------------------------|
| 0 | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` | `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80` |
| 1 | `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` | `0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d` |

Account #0 is used as the deployer (Cannon, TestToken, application registration).
Account #1 holds the initial token supply and is the configured withdrawal address.

### Service ports

| Service     | Port  | Purpose                                          |
|-------------|-------|--------------------------------------------------|
| anvil       | 8545  | EVM JSON-RPC (HTTP + WebSocket)                  |
| advancer    | 10012 | Inspect endpoint (`POST /inspect/{app-name}`)    |
| jsonrpc-api | 10011 | Read API — reports, vouchers, notices            |
