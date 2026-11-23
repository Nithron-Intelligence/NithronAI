---
out: Technik/homelab/docker-compose.yml
format: text
language: en
kind: code
license: CC-BY-4.0
source: written for nai-bench
provenance: claude-authored
---
# Homelab services on the NAS (Ahornweg 7)
# Start: docker compose up -d   Update: docker compose pull && docker compose up -d

services:
  nextcloud:
    image: nextcloud:29-apache
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - /srv/nextcloud/html:/var/www/html
      - /srv/nextcloud/data:/var/www/html/data
    environment:
      - POSTGRES_HOST=db
      - POSTGRES_DB=nextcloud
      - POSTGRES_USER=nextcloud
      - POSTGRES_PASSWORD_FILE=/run/secrets/nextcloud_db_password
    secrets:
      - nextcloud_db_password
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - /srv/nextcloud/db:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=nextcloud
      - POSTGRES_USER=nextcloud
      - POSTGRES_PASSWORD_FILE=/run/secrets/nextcloud_db_password
    secrets:
      - nextcloud_db_password

  jellyfin:
    image: jellyfin/jellyfin:10.9
    restart: unless-stopped
    ports:
      - "8096:8096"
    volumes:
      - /srv/jellyfin/config:/config
      - /mnt/media:/media:ro

  paperless:
    image: ghcr.io/paperless-ngx/paperless-ngx:2.11
    restart: unless-stopped
    ports:
      - "8010:8000"
    volumes:
      - /srv/paperless/data:/usr/src/paperless/data
      - /srv/paperless/consume:/usr/src/paperless/consume
    environment:
      - PAPERLESS_OCR_LANGUAGE=deu+eng+swe
      - PAPERLESS_TIME_ZONE=Europe/Berlin

secrets:
  nextcloud_db_password:
    file: ./secrets/nextcloud_db_password.txt
