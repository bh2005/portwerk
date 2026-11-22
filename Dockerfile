# Stufe 1: Oberfläche bauen
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stufe 2: Backend + gebaute Oberfläche in einem Container
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 OPP_DATA_DIR=/data OPP_STATIC_DIR=/app/static
WORKDIR /app
# Unicode-Schrift für die PDF-Arbeitsanweisung (Umlaute, Pfeile, Kästchen)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY --from=ui /ui/dist ./static
RUN useradd --system --uid 10001 opp && mkdir /data && chown opp /data
USER opp
VOLUME /data
EXPOSE 8084 8443
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8084/health')"
CMD ["python", "-m", "app.serve"]
