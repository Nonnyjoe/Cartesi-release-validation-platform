FROM python:3.12-slim

# Install system tools needed by test executors (curl, docker CLI for exec/restart)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
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
