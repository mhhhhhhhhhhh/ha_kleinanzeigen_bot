FROM debian:trixie-slim
ARG BUILD_ARCH
ARG BUILD_VERSION=0.2.1
ARG BOT_RELEASE=latest
ENV DEBIAN_FRONTEND=noninteractive LANG=de_DE.UTF-8 TZ=Europe/Berlin \
 DISPLAY=:99 PYTHONUNBUFFERED=1 HOME=/data/home
RUN apt-get update && apt-get install -y --no-install-recommends \
 ca-certificates curl tini locales tzdata chromium xvfb x11-utils x11vnc \
 novnc websockify openbox nginx-light python3 python3-flask python3-yaml \
 python3-waitress util-linux fonts-noto-core fonts-noto-color-emoji \
 fonts-dejavu-core fonts-liberation \
 && echo 'de_DE.UTF-8 UTF-8' > /etc/locale.gen && locale-gen \
 && useradd --uid 1000 --home-dir /data/home --no-create-home --shell /usr/sbin/nologin bot \
 && rm -rf /var/lib/apt/lists/*
RUN set -eu; arch="${BUILD_ARCH:-$(dpkg --print-architecture)}"; \
 case "$arch" in amd64) binary_arch=amd64;; aarch64|arm64) binary_arch=arm64;; *) echo "Unsupported: $arch"; exit 1;; esac; \
 curl --fail --location --retry 3 \
 "https://github.com/Second-Hand-Friends/kleinanzeigen-bot/releases/download/${BOT_RELEASE}/kleinanzeigen-bot-linux-${binary_arch}" \
 --output /usr/local/bin/kleinanzeigen-bot; \
 chmod 755 /usr/local/bin/kleinanzeigen-bot; \
 /usr/local/bin/kleinanzeigen-bot version > /opt-bot-version.txt; \
 /usr/local/bin/kleinanzeigen-bot help > /opt-bot-help.txt
COPY app /opt/ha-bot/app
COPY boot.py /opt/ha-bot/boot.py
COPY nginx.conf /etc/nginx/nginx.conf
LABEL io.hass.type="addon" io.hass.version="${BUILD_VERSION}" \
 io.hass.arch="${BUILD_ARCH}" org.opencontainers.image.licenses="AGPL-3.0-or-later"
WORKDIR /data/workspace
EXPOSE 8099
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/bin/python3", "/opt/ha-bot/boot.py"]
