FROM python:3.12-slim

# Docker CLI for log reading via socket
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=shared / /app/shared/
COPY . .

CMD ["python", "-u", "main.py"]
