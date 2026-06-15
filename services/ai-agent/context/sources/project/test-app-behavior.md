# Deployed Application: student-tracker

Every sandbox runs the **student-tracker** dApp (Rust, source `student-tracker/src/main.rs`,
registered with the node as `test-app`). It is a purpose-built test target: a student
registry plus a full portal-deposit/withdrawal ledger that emits **notices, reports AND
real executable vouchers**.

> Historical note: earlier versions of this doc described a minimal echo dApp — that was
> wrong (found as F-2 in the 2026-06-10 manual-execution test report). Payload-echo
> expectations do NOT hold here.

## Advance inputs — JSON actions

The advance payload must be the hex encoding of a UTF-8 **JSON** string. Build it with
`cast` (e.g. payload for `{"action":"ping"}` is `0x` + hex of that string). Valid actions:

| Action | Payload | Behaviour |
|---|---|---|
| `ping` | `{"action":"ping"}` | ACCEPT. Notice `{"event":"pong","input_index":N,"sender":"0x…"}` |
| `register` | `{"action":"register","name":"…","reg_number":"…"}` | ACCEPT. Registers `msg_sender` as a student. Notice `{"event":"student_registered",…}`. REJECTS (with error report) on missing fields or if the wallet is already registered |
| `withdraw` | `{"action":"withdraw","asset_type":"ether","amount":"<wei>"}` (also `erc20`/`erc721`/`erc1155` with `token`/`token_id` fields) | ACCEPT → emits a **voucher** (e.g. `withdrawEther(address,uint256)` targeting the app contract). REJECTS: `not_registered`, `withdraw_invalid_amount`, `insufficient_<asset>_balance` (balance = deposits − withdrawals tracked per wallet) |

Anything else REJECTS with an error report: non-hex payload (`invalid_hex_payload`),
non-UTF-8 (`payload_not_utf8`), non-JSON (`payload_not_json`), unknown action
(`unknown_action` listing `["ping","register","withdraw"]`).

Every **accepted** advance ALSO emits a diagnostic report
`{"event":"advance_processed","input_index":N,"msg_sender":"0x…","result":"accept"}`.

## Portal deposits

Inputs whose `msg_sender` is a portal (Ether/ERC20/ERC721/ERC1155 portal addresses — see
the Sandbox Deployment Manifest) are parsed as portal deposit payloads and credited to the
depositor's ledger. Deposit first (via the portal contract on L1), then `withdraw` to get
an executable voucher — this is the path voucher tests exercise.

## Inspect routes

The inspect payload is the hex of a UTF-8 **route string** (not JSON). Responses come back
as hex-encoded JSON reports with `status: Accepted`:

- `` (empty) or `all` → `{"route":"all","total_students":N,"students":[…]}`
- `student/<0xaddr>` → that student's record, or `{"error":"not_found",…}`
- `activity/<0xaddr>` → the wallet's activity log
- `portals` → portal addresses the app has learned
- `summary` → totals: students, registered, inputs, notices, vouchers, deposits/withdrawals
- `app` → app contract address + version (`2.0.0`)
- `status` / `health` → liveness info
- anything else → `{"error":"unknown_route","valid":["all","student/<addr>","activity/<addr>","portals","app","summary","status"]}`

## Proven command recipes (use these shapes — they are what the test-runner itself uses)

`APP` = manifest Application address, `INPUTBOX` = manifest InputBox,
`KEY` = `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80` (Anvil #0).
JSON payload → hex: e.g. `{"action":"ping"}` → `0x7b22616374696f6e223a2270696e67227d`.

1. **Send an advance input** (run_cast_command):
   `send --private-key KEY INPUTBOX "addInput(address,bytes)" APP 0x<hex-of-json>`
2. **Register** (do this once before withdrawals):
   payload `{"action":"register","name":"Ada Lovelace","reg_number":"CS-1815"}`
3. **Deposit ether** (run_cast_command — funds the withdraw→voucher path):
   `send --private-key KEY --value 1000000000000000000 ETHER_PORTAL "depositEther(address,bytes)" APP 0x`
4. **Withdraw → voucher**:
   payload `{"action":"withdraw","asset_type":"ether","amount":"500000000000000000"}`
   (erc20: + `"token":"0x…"`; erc721: + `"token"`,`"token_id"`; erc1155: + `"token"`,`"token_id"`,`"amount"`)
5. **Confirm indexing / outputs** (call_jsonrpc):
   `cartesi_listInputs {application: APP}` → input status;
   `cartesi_listOutputs {application: APP}` → notices + vouchers (decode `raw_data`).
6. **Inspect** (call_inspect): payload = hex of a route string, e.g. `status` →
   `0x737461747573`.

Test ERC20/721/1155 tokens are pre-deployed (manifest addresses) with a public
`mint(...)` — mint to yourself, `approve`/`setApprovalForAll` the portal, then deposit.

## Judging hints

- Expect REJECT for malformed/raw payloads — that is correct dApp behaviour, not a node bug.
- Notices/vouchers/reports appear via `cartesi_listOutputs` (and report-only results for
  inspect). The input's `status` in `cartesi_listInputs`/`cartesi_listProcessedInputs`
  reflects accept/reject.
- Vouchers ARE producible (deposit → withdraw); voucher-execution tests are meaningful here.
- `msg_sender` matters: `register` keys students by sender wallet; use the default Anvil
  account (`0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`) consistently unless a test needs
  multiple identities (Anvil accounts #1, #2, … are available with well-known keys).
