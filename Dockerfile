FROM python:3.13.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 appuser \
    && useradd \
       --uid 10001 \
       --gid 10001 \
       --create-home \
       --shell /usr/sbin/nologin \
       appuser

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /data \
    && chown -R 10001:10001 /data

USER appuser

EXPOSE 8798

VOLUME ["/data"]

HEALTHCHECK \
  --interval=30s \
  --timeout=5s \
  --start-period=10s \
  --retries=3 \
  CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8798/health', timeout=2)"]

CMD ["python","-m","app"]
