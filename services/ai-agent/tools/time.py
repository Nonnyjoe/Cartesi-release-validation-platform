"""
tools/time.py
advance_time — move Anvil block time forward to trigger epoch close
"""
import asyncio
import logging
from typing import Any

log = logging.getLogger("ai-agent.tools.time")

EPOCH_LENGTH_BLOCKS = 7200


async def advance_time(
    blocks: int,
    anvil_rpc_url: str,
    seconds_per_block: int = 1,
) -> dict[str, Any]:
    """
    Mine N blocks on Anvil to advance chain time.
    Uses cast rpc anvil_mine for reliable block advancement.
    blocks: number of blocks to mine (7200 = one full epoch)
    """
    log.info("Advancing Anvil by %d blocks (≈ %ds)...", blocks, blocks * seconds_per_block)

    # Get current block before
    before = await _get_block_number(anvil_rpc_url)

    # Mine blocks in batches to avoid timeouts
    batch_size = 500
    mined = 0
    while mined < blocks:
        batch = min(batch_size, blocks - mined)
        proc = await asyncio.create_subprocess_shell(
            f"cast rpc anvil_mine {batch} --rpc-url {anvil_rpc_url}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"anvil_mine failed: {stderr.decode().strip()}",
                "mined_so_far": mined,
            }
        mined += batch

    after = await _get_block_number(anvil_rpc_url)
    return {
        "success": True,
        "blocks_requested": blocks,
        "blocks_mined": mined,
        "block_before": before,
        "block_after": after,
        "epochs_advanced": mined // EPOCH_LENGTH_BLOCKS,
    }


async def _get_block_number(anvil_rpc_url: str) -> int | None:
    try:
        proc = await asyncio.create_subprocess_shell(
            f"cast block-number --rpc-url {anvil_rpc_url}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return int(stdout.decode().strip())
    except Exception:
        return None
