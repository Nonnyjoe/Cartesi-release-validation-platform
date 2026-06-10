# Cartesi JSON-RPC API — Quick Reference (v2.x)

POST to `http://rvp-jsonrpc-{short_id}:10011` with:
```json
{"jsonrpc": "2.0", "id": 1, "method": "<method>", "params": [...]}
```

Use the `call_jsonrpc` tool. Method must start with `cartesi_`.

## Methods

| Method | Params | Returns |
|---|---|---|
| `cartesi_listApplications` | `[]` | `{ data: [ { applicationAddress, deployer, ... } ], pagination }` |
| `cartesi_getApplication` | `[app_address]` | `{ applicationAddress, status, latestProcessedBlock, ... }` |
| `cartesi_listInputs` | `[app_address, { limit?, offset? }?]` | `{ data: [Input], pagination }` |
| `cartesi_getInput` | `[app_address, input_index_hex]` | `Input` |
| `cartesi_listEpochs` | `[app_address, { limit?, offset? }?]` | `{ data: [Epoch], pagination }` |
| `cartesi_getEpoch` | `[app_address, epoch_index_hex]` | `Epoch` |
| `cartesi_getLastAcceptedEpochIndex` | `[app_address]` | `{ data: int }` |
| `cartesi_getProcessedInputCount` | `[app_address]` | `{ data: int }` |
| `cartesi_listOutputs` | `[app_address, { limit?, offset?, type?, inputIndex? }?]` | `{ data: [Output], pagination }` |
| `cartesi_getOutput` | `[app_address, output_index_hex]` | `Output` |
| `cartesi_listReports` | `[app_address, { limit?, offset?, inputIndex? }?]` | `{ data: [Report] }` |
| `cartesi_getReport` | `[app_address, report_index_hex]` | `Report` |
| `cartesi_getChainId` | `[]` | `{ data: hex }` |
| `cartesi_getNodeVersion` | `[]` | `{ data: string }` |

## Key shapes

### Input
```
{
  index: int,
  inputBoxIndex: int,
  appAddress: string,
  sender: string,
  payload: hex,
  status: "NONE" | "ACCEPTED" | "REJECTED" | ...,
  blockNumber: int,
  epochIndex: int,
  timestamp: int
}
```

### Output
```
{
  index: int,
  inputIndex: int,
  type: "NOTICE" | "VOUCHER" | "DELEGATE_CALL_VOUCHER",
  payload: hex,
  status: "NONE" | "ACCEPTED" | "EXECUTED",
  proof: { ... } | null
}
```

### Epoch
```
{
  index: int,
  appAddress: string,
  firstBlock: int,
  lastBlock: int,
  status: "OPEN" | "CLOSED" | "INPUTS_PROCESSED" | "CLAIMED" | "ACCEPTED",
  claimHash: hex | null,
  claimTransactionHash: hex | null
}
```

## Hex encoding pitfalls

- `epoch_index` and `input_index` must be **hex strings** in params: `"0x0"` not `0`.
- Use `hex(n)` in Python or `"0x" + n.toString(16)` in JS.
- Pagination `limit`/`offset` are plain integers.

## Common errors

| Error message | Cause | Fix |
|---|---|---|
| `Epoch not found` | No accepted epoch yet | Poll with `cartesi_getLastAcceptedEpochIndex` |
| `Invalid epoch index: expected hex encoded value` | Passed an integer instead of hex | Convert with `hex(idx)` |
| `Application not found` | Wrong app address | Call `cartesi_listApplications` first |

## Useful flows

**Wait for an input to be accepted**:
1. Submit via `send_advance_input`.
2. Poll `cartesi_getInput(app, hex(idx))` until `status == "ACCEPTED"`.

**Wait for an epoch to be claimed**:
1. Poll `cartesi_getLastAcceptedEpochIndex(app)` until it returns a value ≥ target.
2. Or poll `cartesi_listEpochs` and look for `status == "CLAIMED"` or `"ACCEPTED"`.

**Find a notice produced by input N**:
1. `cartesi_listOutputs(app, { inputIndex: N, type: "NOTICE" })`.
2. Decode the hex `payload` to bytes.
