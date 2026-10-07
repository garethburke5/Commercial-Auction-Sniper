FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=UTC
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr ca-certificates gosu && rm -rf /var/lib/apt/lists/*
COPY web_platform/requirements.txt /app/web_platform/requirements.txt
RUN pip install --no-cache-dir -r web_platform/requirements.txt
COPY . /app
RUN useradd --create-home --uid 10001 sniper && mkdir -p /var/data && chown sniper:sniper /var/data
ENV ACCOUNT_DATABASE_PATH=/var/data/accounts.sqlite PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "chown sniper:sniper /var/data && exec gosu sniper uvicorn web_platform.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
