---
id: erc20-deposit-v2
name: ERC20 Portal Deposit (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc20, assets, v2]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc20
    amount: 1000000
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
Deploys a minimal ERC20 test token on the sandbox Anvil, mints tokens to Anvil
account #0, approves the ERC20Portal, then calls `depositERC20Tokens`.  Verifies
the Cartesi node indexes the resulting input.

## Steps
1. Spawn a Foundry container in the Anvil network namespace.
2. Deploy `TestERC20.sol` via `forge create`, mint 1 000 000 tokens to the sender.
3. `approve(ERC20Portal, 1_000_000)` then call `depositERC20Tokens(token, app, 1_000_000, 0x)`.
4. Poll `cartesi_listInputs(app_address)` and assert at least 1 input is present.

## Expected Behaviour
- All three `cast send` transactions succeed.
- The node's JSON-RPC API returns ≥1 inputs after the deposit.

## Notes
Uses `ghcr.io/foundry-rs/foundry:latest` for compilation.  Docker socket must be
mounted into the test-runner container.  Foundry container shares the Anvil
container's network namespace so `localhost:8545` reaches the sandbox chain.
