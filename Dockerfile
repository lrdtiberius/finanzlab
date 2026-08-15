FROM python:3.13-slim
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser app ./app
RUN mkdir /data && chown appuser:appuser /data
USER appuser
ENV PORT=8798 DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8798
VOLUME ["/data"]
HEALTHCHECK CMD ["python","-c","import urllib.request;urllib.request.urlopen('http://127.0.0.1:8798/health')"]
CMD ["python","-m","app"]
