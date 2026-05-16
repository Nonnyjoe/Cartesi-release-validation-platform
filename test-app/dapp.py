"""
test-app/dapp.py
Minimal Cartesi echo dapp used as the machine snapshot for v2.x sandbox testing.

This application echoes back any input payload as a notice and advances the state.
It is deliberately simple — the goal is to give the advancer a valid machine to
load, so the full 6-service SDK stack can start successfully.

Build with:
  cd test-app && cartesi build
The resulting snapshot lands in test-app/.cartesi/image/
"""
import sys
import json

from cartesi import DApp, Rollup, RollupData, URLRouter

dapp = DApp()
router = URLRouter()


@dapp.advance()
def handle_advance(rollup: Rollup, data: RollupData) -> bool:
    payload = data.payload  # hex-encoded input
    rollup.notice(payload)  # echo it back as a notice
    return True


@dapp.inspect()
def handle_inspect(rollup: Rollup, data: RollupData) -> bool:
    rollup.report(b"echo-dapp ready")
    return True


if __name__ == "__main__":
    dapp.run()
