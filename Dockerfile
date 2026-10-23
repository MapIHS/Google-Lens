FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GOOGLE_LENS_PROFILE_DIR=/profile \
    GOOGLE_LENS_CHROMIUM=/usr/bin/chromium

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    ca-certificates \
    fonts-liberation \
    xvfb \
    xauth \
    novnc \
    websockify \
    x11vnc \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 worker \
    && useradd --uid 10001 --gid worker --create-home --shell /usr/sbin/nologin worker

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py google_lens_scraper.py start-worker.sh ./
RUN chmod 755 /app/start-worker.sh && mkdir -p /profile && chown worker:worker /profile /app

USER worker:worker
EXPOSE 8787 6080
CMD ["/app/start-worker.sh"]
