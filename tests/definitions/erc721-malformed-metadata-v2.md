---
id: erc721-malformed-metadata-v2
name: ERC721 deposit with malformed metadata — handled gracefully (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc721, error-handling, v2, phase3]
csv_ids: ["3.12"]
release_introduced: v2.0.0
component: advancer
priority: low
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc721
    token_id: 3
    base_layer_data: "0xdeadbeef"
    exec_layer_data: "0xffffffff"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 3.12 — Deposit an ERC721 token with intentionally malformed/corrupt
metadata (non-ABI-encoded base and exec layer data) and verify the node handles
this gracefully without crashing.

## Steps
1. Deposit ERC721 token #42 with random hex as baseLayerData + execLayerData.
2. Assert the input is still indexed (even if the app rejects it internally).

## Expected Behaviour
- Portal deposit transaction succeeds (malformed data does not prevent deposit).
- Input is indexed by the node's JSON-RPC.
- Node does not crash or panic on corrupt metadata.
