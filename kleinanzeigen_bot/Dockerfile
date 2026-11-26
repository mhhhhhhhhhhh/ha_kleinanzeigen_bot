FROM debian:trixie-slim
ARG BUILD_ARCH
ARG BUILD_VERSION=0.2.0
# Set to a full commit SHA for reproducible upstream selection.
ARG BOT_REF=main
ENV DEBIAN_FRONTEND=noninteractive LANG=de_DE.UTF-8 TZ=Europe/Berlin \
    DISPLAY=:99 PYTHONUNBUFFERED=1 HOME=/data/home \
    PATH=/opt/venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git tini locales tzdata chromium xvfb x11-utils x11vnc \
    novnc websockify openbox nginx-light python3 python3-venv python3-flask \
    python3-yaml python3-waitress python3-pil util-linux fonts-noto-core \
    fonts-noto-color-emoji fonts-dejavu-core fonts-liberation \
    && echo 'de_DE.UTF-8 UTF-8' > /etc/locale.gen && locale-gen \
    && useradd --uid 1000 --home-dir /data/home --no-create-home --shell /usr/sbin/nologin bot \
    && rm -rf /var/lib/apt/lists/*
# Install from source: avoids the incorrect aarch64 release filename and
# applies upstream's required nodriver patch. Record exact source + dependencies.
RUN set -eu; \
    git init /opt/upstream; \
    cd /opt/upstream; \
    git remote add origin https://github.com/Second-Hand-Friends/kleinanzeigen-bot.git; \
    git fetch --depth=1 origin "${BOT_REF}"; \
    git checkout --detach FETCH_HEAD; \
    git rev-parse HEAD > /opt-bot-commit.txt; \
    python3 -m venv --system-site-packages /opt/venv; \
    /opt/venv/bin/python -m pip install --no-cache-dir .; \
    /opt/venv/bin/python scripts/fix_nodriver.py; \
    /opt/venv/bin/python -m pip freeze > /opt-bot-dependencies.txt
COPY bot-entry.sh /usr/local/bin/kleinanzeigen-bot
RUN chmod 755 /usr/local/bin/kleinanzeigen-bot \
    && /usr/local/bin/kleinanzeigen-bot version > /opt-bot-version.txt \
    && /usr/local/bin/kleinanzeigen-bot help --lang=en > /opt-bot-help.txt \
    && grep -Eq '^[[:space:]]*list[[:space:]]+-' /opt-bot-help.txt \
    && grep -Eq '^[[:space:]]*extend[[:space:]]+-' /opt-bot-help.txt
COPY app /opt/ha-bot/app
COPY boot.py /opt/ha-bot/boot.py
COPY nginx.conf /etc/nginx/nginx.conf
LABEL io.hass.type="addon" io.hass.version="${BUILD_VERSION}" \
    io.hass.arch="${BUILD_ARCH}" org.opencontainers.image.licenses="AGPL-3.0-or-later"
WORKDIR /data/workspace
EXPOSE 8099
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/venv/bin/python", "/opt/ha-bot/boot.py"]
