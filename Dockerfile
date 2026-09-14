FROM python:3.13-slim
LABEL org.opencontainers.image.title="FinanzLab" \
      org.opencontainers.image.version="1.6.1"
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser VERSION ./VERSION
RUN mkdir /data && chown appuser:appuser /data
USER appuser
ENV PORT=8798 \
    DATA_DIR=/data \
    ENERGYLAB_SYNC_INTERVAL_SECONDS=21600 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8798
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8798/health', timeout=2)"]
CMD ["python","-m","app"]
