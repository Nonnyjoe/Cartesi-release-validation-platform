# Cartesi Rollups Node — Architecture Reference

## Overview
The Cartesi rollups node is a set of co-operating services that bridge an
Ethereum-compatible chain (L1) with a Cartesi Machine (the off-chain compute
environment). Together they implement an optimistic rollup protocol.

## Core Components

### Dispatcher
Watches the InputBox smart contract on L1 for new inputs (advance-state calls).
When a new input arrives it forwards the payload to the Cartesi Machine for
processing and records the resulting outputs (notices, vouchers, reports).

### Cartesi Machine
The deterministic off-chain virtual machine that executes the dApp logic.
It reads inputs and produces outputs in a reproducible way — any verifier
running the same machine on the same inputs must reach the same state.

### Authority Claimer
After each epoch closes (determined by the epoch length in blocks), the
authority claimer generates the output Merkle tree root for all outputs in
that epoch and submits a Claim transaction to the consensus contract on L1.

### GraphQL Server
Exposes a GraphQL API that indexes all on-chain and off-chain data — inputs,
outputs (notices, vouchers, reports), epochs, and claims. Used by frontends
and the test runner to query node state.

### Inspect Server
Provides a synchronous REST endpoint (`/inspect/<payload>`) that allows
querying the current dApp state without sending an L1 transaction. Inspect
calls do not change state.

### State Server
Manages the internal state of the node — current epoch, input counts,
pending outputs. Acts as the source of truth for the other components.

## Key Contracts (Anvil dev chain addresses)

| Contract | Address |
|---|---|
| InputBox | 0x59b22D57D4f067708AB0c00552767405926dc768 |
| CartesiDApp (example) | 0x0000000000000000000000000000000000000001 |
| Authority | 0x0000000000000000000000000000000000000002 |

## Epoch Lifecycle
1. Epoch opens when the previous one closes (or at genesis)
2. Inputs accumulate in the epoch
3. Epoch closes when `epoch_length` blocks pass on L1
4. Authority Claimer submits a Claim with the output Merkle root
5. After the dispute window (optimistic), vouchers in the epoch can be executed

## Ports (inside sandbox)
| Service | Port |
|---|---|
| Anvil RPC | 8545 |
| Node HTTP (advance + inspect) | 5004 |
| GraphQL | 4000 |
