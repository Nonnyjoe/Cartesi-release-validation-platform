# Cannon Deployer — curl Download Failure

## Problem

When a v2.x sandbox is provisioned, the cannon-deployer container downloads the
`rollups-contracts` source tarball from GitHub to compile and deploy on-chain:

```bash
curl -fsSL \
  "https://github.com/cartesi/rollups-contracts/archive/refs/tags/${TAG}.tar.gz" \
  -o "${TMP}/src.tar.gz"
```

This fails intermittently with:

```
curl: (18) HTTP/2 stream 1 was not closed cleanly before end of the underlying stream
```

Exit code `18` is curl's "partial file" error — the TCP connection is dropped or
the HTTP/2 stream is closed by the server before the file transfer completes.
The download is not retried and the deployer exits with code 18, causing the
entire sandbox provisioning to fail at the `contracts_failed` step.

### Observed behaviour

- Failure is **intermittent** — the same run sometimes succeeds, sometimes fails
  depending on GitHub CDN / network conditions
- The error appears at the very start of the download (stream 1, first request)
- Exit code is always `18`; no partial file is written
- The cannon deployer itself (soldeer, cannon build, address extraction) is never
  reached

### Context

The failure is visible in the sandbox run events under `contracts_failed`:

```json
{
  "step": "contracts_failed",
  "detail": {
    "reason": "Contract deployment exited 18. Last stderr:
      [cannon-deployer] Waiting for Anvil at http://localhost:8545...
      [cannon-deployer] Anvil is reachable (attempt 1/10)
      [cannon-deployer] Downloading rollups-contracts v2.2.0...
      curl: (18) HTTP/2 stream 1 was not closed cleanly before end of the underlying stream"
  }
}
```

The provisioner (sandbox-manager) previously also surfaced this as
`UnixHTTPConnectionPool: Read timed out` because the docker-py client's default
60-second HTTP read timeout fired before the cannon container exited (~2-3 min).
That masking issue has since been fixed by setting `docker.from_env(timeout=600)`.

---

## Attempted fixes

### 1. Increased docker-py client timeout (`provisioner.py`)

**Change:** `docker.from_env(timeout=600)` instead of default 60 s.

**Effect:** Unmasked the real error. Previously the provisioner reported a
docker-py read timeout; now it correctly surfaces the curl exit code and stderr.

**Status:** Applied and working — no longer masks the underlying failure.

---

## Potential fixes (not yet applied)

### A. Disable HTTP/2 (`--http1.1`)

Force curl to use HTTP/1.1 for the GitHub download, avoiding the HTTP/2 stream
closure issue entirely:

```bash
curl -fsSL --http1.1 \
  "https://github.com/.../rollups-contracts-${TAG}.tar.gz" \
  -o "${TMP}/src.tar.gz"
```

**File:** `sandbox-base/cannon-deployer/deploy-contracts.sh`, line 57.

**Pros:** Simplest fix; HTTP/2 multiplexing provides no benefit for a single
large file download.  
**Cons:** Marginally slower on a good connection (no HPACK header compression).

### B. Add curl retry

```bash
curl -fsSL --retry 3 --retry-delay 2 --retry-all-errors \
  "https://github.com/.../rollups-contracts-${TAG}.tar.gz" \
  -o "${TMP}/src.tar.gz"
```

**Pros:** Handles transient failures without needing to re-trigger the whole run.  
**Cons:** Adds up to ~6 s delay on consistent failures; does not fix the root
cause.

### C. Both A + B (recommended)

```bash
curl -fsSL --http1.1 --retry 3 --retry-delay 2 \
  "https://github.com/.../rollups-contracts-${TAG}.tar.gz" \
  -o "${TMP}/src.tar.gz"
```

Eliminates the HTTP/2 issue and handles any remaining transient failures.
After changing the script the cannon-deployer image must be removed and rebuilt:

```bash
docker rmi rvp-cannon-deployer:v2.2.0
# next run will rebuild it automatically
```

### D. Bundle the tarball in the image at build time

Pre-download the contracts tarball during `docker build` rather than at runtime.
This removes the runtime network dependency entirely but means a new image must
be built for each `contracts_version`.

---

## Files involved

| File | Role |
|------|------|
| `sandbox-base/cannon-deployer/deploy-contracts.sh` | The curl call is on line 57 |
| `sandbox-base/cannon-deployer/Dockerfile` | Image built by `_ensure_cannon_deployer_image_sync()` |
| `services/sandbox-manager/provisioner.py` | `_deploy_contracts_sync()` — runs the container and waits |
