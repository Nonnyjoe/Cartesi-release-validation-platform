FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=shared / /app/shared/
COPY . .

CMD ["python", "-u", "main.py"]
