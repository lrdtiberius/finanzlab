# Portable release: no dependency on a private previous FinanzLab image.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8798
RUN groupadd --system --gid 10001 appuser && \
    useradd --system --uid 10001 --gid appuser --home /app appuser && \
    mkdir -p /data && chown appuser:appuser /data
WORKDIR /app
COPY --chown=appuser:appuser app/ /app/app/
COPY --chown=appuser:appuser VERSION /app/VERSION
USER appuser
VOLUME ["/data"]
EXPOSE 8798
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8798/health', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
