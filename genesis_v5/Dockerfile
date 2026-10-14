FROM python:3.12-slim

# Genesis V5 — offline-capable, secret-free image.
# Runtime secrets are passed via environment, never baked into the image.

WORKDIR /srv/genesis

COPY pyproject.toml README.md ./
COPY genesis ./genesis

# `requests` is optional (only needed when provider adapters contact real
# endpoints); the offline core runs with no third-party dependencies.
RUN pip install --no-cache-dir . 2>/dev/null || pip install --no-cache-dir -e . || true

ENV GENESIS_OFFLINE=true \
    GENESIS_ENV=production \
    GENESIS_DATA_DIR=/data

VOLUME ["/data"]

EXPOSE 8000

COPY docker/entrypoint.sh /usr/local/bin/genesis-entrypoint
RUN chmod +x /usr/local/bin/genesis-entrypoint

ENTRYPOINT ["genesis-entrypoint"]
CMD ["serve"]