FROM python:3.12-slim

# Install system tools needed by test executors (curl for healthchecks, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# NOTE: @cartesi/cli is NOT installed here.
# The provisioner builds a per-release cartesi-rvp-cli:<cli_version> Docker image
# and runs it as a cli-tools sidecar in each sandbox's Docker network.
# Test executors access it via SandboxContext.cli_container_name.

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=shared / /app/shared/
COPY . .

CMD ["python", "-u", "main.py"]
