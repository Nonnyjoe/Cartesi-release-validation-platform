FROM python:3.12-slim

# Need Docker CLI inside this container (to call host Docker socket)
RUN apt-get update && apt-get install -y --no-install-recommends docker.io git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=shared / /app/shared/
COPY . .

CMD ["python", "-u", "main.py"]
