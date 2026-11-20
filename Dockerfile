# AutoSaga in server mode, for a NAS: every computer on the office network opens the page.
# README-NAS.md has every step. Built on the NAS from the cloned repository:
#   docker compose up -d --build   (or Container Manager > Project > Build)
#
# What the container expects, all of it outside the image:
#   /config   config.toml and tokens.json (the ANAF login)
#   /data     the database, the invoices, the archive and the log
#   /saga     the folder for SAGA, shared with the PCs
#   /backups  the backups
FROM python:3.12-slim

# tini collects the processes a restore leaves behind; tzdata lets TZ give the office's hours.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini tzdata \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.5

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# The page is built already: src/efactura/ui is part of every release.
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    EFACTURA_CONFIG=/config/config.toml \
    EFACTURA_IN_CONTAINER=1 \
    EFACTURA_KEEPER=1 \
    TZ=Europe/Bucharest \
    PYTHONUNBUFFERED=1

EXPOSE 8765
ENTRYPOINT ["tini", "--"]
# Server mode, started again after a restore or a crash (see src/efactura/keeper.py).
# EFACTURA_KEEPER above tells every command in the container, a restore run by hand with
# `docker exec` too, to leave starting the program again to the keeper.
CMD ["efactura", "keep-serving"]
