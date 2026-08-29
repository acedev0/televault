FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TELEVAULT_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY televault ./televault
COPY pyproject.toml README.md ./

RUN useradd --system --uid 10001 --home-dir /data --create-home televault \
    && chown -R televault:televault /data /app
USER televault

EXPOSE 8181
VOLUME ["/data"]
CMD ["uvicorn", "televault.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8181", "--workers", "1", "--no-proxy-headers"]

