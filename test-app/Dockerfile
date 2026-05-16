# ─────────────────────────────────────────────────────────────────
#  Cartesi RVP — Minimal Test Application
#  A simple echo dapp used as the machine snapshot for v2.x testing.
#  Build this image with `cartesi build` from the test-app/ directory.
# ─────────────────────────────────────────────────────────────────
FROM cartesi/python:3.12

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt --no-cache-dir

COPY . .

ENTRYPOINT ["python", "dapp.py"]
