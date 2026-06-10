# Test Application — Echo dApp

The application running inside every sandbox is the same minimal echo dApp at
`test-app/dapp.py` in the repo.

## Advance handler
Receives an input payload and emits a single **Notice** whose payload equals the input payload.

```
input payload  →  notice(payload)
```

So if you send `0xdeadbeef` via `chain_tx` or `send_advance_input`, the next
`cartesi_listOutputs(app, { type: "NOTICE", inputIndex: N })` returns one notice with
`payload == "0xdeadbeef"`.

## Inspect handler
Always returns the bytes `b"echo-dapp ready"` (hex: `0x6563686f2d64617070207265616479`) as a
Report. The inspect query input is ignored.

## Implications for testing

- You can verify the node end-to-end with arbitrary payloads — the notice should always match.
- Notices are immediate after the advance is accepted; vouchers are not produced by this dApp.
- `expect_output_contains`-style checks should match the hex of your payload (or substring).

## When to expect failure
The echo dApp does not produce vouchers, delegate-call vouchers, or revert. If a test fails on
those it is a node-level issue, not a dApp issue.
