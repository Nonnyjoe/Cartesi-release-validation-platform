---
id: mint-nft-voucher-v2
name: Execute mint NFT voucher (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, voucher, nft, mint, v2, phase7]
csv_ids: ["7.15"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
  - claimer
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a226d696e745f6e6674222c22726563697069656e74223a2230783134313435393236353335383937393332333834363236343338333236353733373232313336333032227d"
    comment: '{"action":"mint_nft","recipient":"0x14145926535897932384626438326573721363302"}'
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 120
    comment: "safeMint(address,uint256) voucher targeting the NFT contract"
---

## Description
CSV test 7.15 — Application emits a voucher that mints a new NFT on an L1 contract.

## Steps
1. Send a mint_nft action JSON payload.
2. Poll cartesi_listOutputs for a mint voucher.
3. Voucher contains `safeMint(address,uint256)` calldata targeting the NFT contract.

## Expected Behaviour
- Application generates a mint voucher with correct ABI-encoded calldata.
- Voucher appears in cartesi_listOutputs within 120s.
