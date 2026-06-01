---
id: ether-deposit-v2
name: Ether Portal Deposit (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, ether, assets, v2]
csv_ids: ["3.3"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: ether
    amount: 1000000000000000000
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
Verifies that the EtherPortal contract accepts an Ether deposit from the sandbox
Anvil and that the Cartesi node indexes the resulting input.

## Steps
1. Call `EtherPortal.depositEther(app, 0x)` with 1 ETH from Anvil account #0.
2. Poll `cartesi_listInputs(app_address)` and assert at least 1 input is present.

## Expected Behaviour
- The `depositEther` transaction succeeds (receipt status=1).
- The node's JSON-RPC API returns ≥1 inputs after the deposit.

## Notes
The EtherPortal address is threaded from the sandbox provisioner.
Defaults to the deterministic CREATE2 address `0xA632c5c05812c6a6149B7af5C56117d1D2603828`
when cannon-deployer extraction is unavailable.
