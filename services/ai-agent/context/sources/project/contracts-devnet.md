# Sandbox Devnet — Pinned Contract Addresses

The sandbox Anvil chain is deterministic. These addresses are reproducible on every fresh
sandbox unless the provisioner changes its CREATE2 inputs.

## Core (v2.x)

| Contract | Address |
|---|---|
| InputBox | `0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac` |
| AuthorityFactory | `0x5E96408CFE423b01dADeD3bc867E6013135990cc` |
| ApplicationFactory | `0x26E758238CB6eC5aB70ce0dd52aF2d7b82e1972E` |
| SelfHostedApplicationFactory | `0x010D3CbB4223F5bCc7b7B03cEE59f3aAea8eDb8A` |

## Portals (v2.x, CREATE2 deterministic)

| Portal | Address |
|---|---|
| EtherPortal | `0xA632c5c05812c6a6149B7af5C56117d1D2603828` |
| ERC20Portal | `0xACA6586A0Cf05bD831f2501E7B4aea550dA6562D` |
| ERC721Portal | `0x9E8851dadb2b77103928518846c4678d48b5e371` |
| ERC1155Portal | `0x18558398Dd1a8cE20956287a4DA7B76aE7A96662` |

## Test tokens (deployed per sandbox)

Test ERC20/721/1155 tokens are deployed by the provisioner inside each sandbox. Their addresses
are **not** fixed — fetch them at runtime via:
- `query_db` against `orchestrator.sandboxes.runtime_meta->'token_addresses'`
- or `get_node_state` → `runtime_meta.erc20_token_address` etc.
- or via cli_command template vars `{erc20_token_address}`, `{erc721_token_address}`,
  `{erc1155_token_address}` when constructing test assertions.

## Application address

Each sandbox deploys exactly one application via the ApplicationFactory. To find its address:

```
call_jsonrpc(method="cartesi_listApplications", params=[])
# → { result: { data: [ { applicationAddress: "0x...", ... } ] } }
```

The app address is also stored in `orchestrator.sandboxes.runtime_meta->>'app_address'`.

## Default Anvil accounts

Anvil seeds 10 accounts each with 10000 ETH. Account #0 is used by the test-runner for all
transactions and has:
- Address: `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`
- Private key: `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`

## Useful function selectors

- `InputBox.addInput(address app, bytes payload)` → `0x1789cd63`
- `EtherPortal.depositEther(address app, bytes execLayerData)` → calldata starts at 0x...
- `ERC20Portal.depositERC20Tokens(IERC20 token, address app, uint256 amount, bytes execLayerData)`
