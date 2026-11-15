FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    RADAR_SEED=/app/data/seed.json RADAR_HISTORY=/app/data/observations.jsonl \
    RADAR_IMAGE_DIR=/data/images RADAR_FETCH_IMAGES=1 TZ=Europe/Madrid
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY data/seed.json data/observations.jsonl ./data/
RUN useradd -r -u 10001 radar && mkdir -p /data/images && chown -R radar /data
USER radar
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/meta')"
CMD ["uvicorn", "--factory", "radar.web.app:build_from_env", "--host", "0.0.0.0", "--port", "8080"]
