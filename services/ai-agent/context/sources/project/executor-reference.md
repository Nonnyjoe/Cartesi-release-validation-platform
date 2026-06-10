# Test Runner Executors — Parameter Reference

The test-runner service ships 14 assertion executors. When you invoke `trigger_test`, the
`parameter_overrides` you pass are merged by leaf-name into the assertion array of the test
definition. Use this reference to know what is overridable.

## chain_tx (chain.py)
Submits an input to InputBox.addInput via `eth_sendTransaction` to Anvil.
- **payload** (string, hex): the input bytes. Override to inject custom payloads.
- **expect_revert** (bool): assert the transaction reverts.
- **repeat** (int): submit the payload N times back-to-back.
- **app_address** (string, optional): override the target application address.

## json_rpc (jsonrpc.py)
Calls Cartesi JSON-RPC API (`cartesi_*` methods at port 10011).
- **method** (string, required): e.g. `cartesi_listInputs`, `cartesi_getEpoch`,
  `cartesi_getLastAcceptedEpochIndex`, `cartesi_listApplications`, `cartesi_getOutput`.
- **params** (list|dict): method params.
- **use_app_address** (bool): inject the sandbox's app address as the first param.
- **use_last_epoch** (bool): poll `cartesi_getLastAcceptedEpochIndex` and inject the result as a
  param. Use when you need to query data for the latest accepted epoch.
- **expect_count** (int): expected length of `result.data` array.
- **expect_has_field** (string): JSON path that must be present (e.g. `data` for arrays).
- **path** + **value**: jq-like path + expected value on the response.
- **poll_timeout** (seconds, default 0): retry on error/missing field up to N seconds.
- **pagination_limit / pagination_offset**: page over `result.data`.

## notice_check (notice_check.py)
Polls `cartesi_listOutputs` for Notice outputs.
- **min_count** (int, default 1): minimum notices expected.
- **contains_text** (string|list): hex substring(s) the notice must contain.
- **poll_timeout** (seconds, default 60).
- **poll_interval** (seconds, default 2).

## cli_command (cli_command.py)
`docker exec rvp-cli-{short_id} {binary} {args}`. Template vars available in `args`:
`{anvil_rpc_url}`, `{app_address}`, `{inputbox_address}`, `{erc20_token_address}`,
`{erc721_token_address}`, `{erc1155_token_address}`, `{jsonrpc_container}`.
- **binary** (string): one of `cartesi-rollups-cli`, `cast`, `forge`, `bash`.
- **container** (string, optional): override container name (default `rvp-cli-*`).
- **args** (string): command arguments.
- **expect_exit_code** (int, default 0).
- **expect_output_contains** (string|list).
- **expect_output_not_contains** (string|list).
- **poll_timeout** (seconds, default 0): retry until success or timeout.
- **poll_interval** (seconds, default 15).

## inspect_query (inspect_query.py)
POSTs/GETs to the advancer's `/inspect/{app}/{query}` endpoint.
- **query** (string, hex or text): the inspect query.
- **method** (`POST` | `GET`, default `POST`).
- **expect_json_field** (string): JSON path that must exist in decoded report.
- **expect_json_value** (string): expected value at `expect_json_field`.
- **expect_contains** (string|list): substrings expected anywhere in the decoded report.
- **concurrent** (int, default 1): fan out N concurrent inspect calls.

## portal_deposit (portal_deposit.py)
Sends a deposit via the relevant portal contract.
- **token_type** (`ether` | `erc20` | `erc721` | `erc1155`).
- **amount** (string|int).
- **token_id** (int, for erc721/erc1155).

## voucher / voucher_v2 (voucher.py, voucher_v2.py)
Queries GraphQL (v1.x) or JSON-RPC (v2.x) for vouchers; v2.x also verifies the Merkle proof.
- **expect_count** (int).

## graphql (graphql.py)
POST a GraphQL query, assert a JSON path equals a value.
- **query** (string, GraphQL).
- **expect** (object): `{ path: string, value: any }`.

## http_status (http.py)
Simple HTTP GET → status code check.
- **endpoint** (string, URL path).
- **expect** (int, status code).
- **port_override** (int, optional).

## log_contains (log.py)
Tails a container's logs and asserts a regex pattern.
- **pattern** | **text** (string).
- **component** | **service** (string, e.g. `advancer`, `claimer`, `validator`, `jsonrpc-api`,
  `evm-reader`).
- **expect_absent** (bool): assert pattern does NOT appear.
- **timeout_seconds** (int).
- **tail** (int, default 200).

## health_check (health_check.py)
GET `/healthz` on a v2.x service.
- **service** (`advancer` | `claimer` | `validator` | `jsonrpc-api` | `evm-reader`).
- **path** (default `/healthz`).
- **expect_status** (int, default 200).
- **expect_body_contains** (string, optional).

## metrics_check (metrics_check.py)
Fetches `/metrics` and validates Prometheus format.
- **service** (same enum as health_check).
- **expect_metric** (string): metric name that must exist.
- **expect_metric_changed** (bool): metric value must change between two reads.
- **expect_format_valid** (bool, default true).

## service_restart (service_restart.py)
Restarts a container and polls health until ready.
- **service** (string).
- **verify_path** (string, default `/healthz`).
- **verify_timeout** (int).
- **pre_inputs_required** (int): submit N inputs before restart.

## How parameter_overrides work in trigger_test

When you call `trigger_test(definition_slug="echo-ping-v2", parameter_overrides={...})`, the
test-runner walks the assertion array and replaces matching leaves. Example:

```yaml
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"          # baseline
  - type: notice_check
    min_count: 1
```

If you pass `parameter_overrides={"payload": "0xCAFE", "min_count": 3}`, the run uses payload
`0xCAFE` and asserts ≥3 notices.

Keys you pass must match leaf names in the YAML. Nested paths like
`assertions.0.payload` are also accepted for disambiguation.
