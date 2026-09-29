# Deploying Tahaqqaq on a Hostinger VPS

The app is a long-running Flask service with a background worker, Redis, Postgres,
headless Chromium and an embedding model. It needs a **VPS**; Hostinger's shared and
cloud web-hosting plans cannot run it.

## 1. The server

| Item | Choice |
|---|---|
| Plan | KVM 2 (2 vCPU, 8 GB RAM) or larger. 4 GB works only with `INSTALL_ML=false`. |
| OS template | Ubuntu 24.04 with Docker |
| Disk | 40 GB or more (the image is about 4 GB with the model runtime) |
| Firewall | allow 22, 80, 443 only |

Point your domain at the server: an `A` record for the host name to the VPS IP.
HTTPS certificates are issued automatically on first start.

## 2. First deployment

```bash
ssh root@YOUR_SERVER_IP
git clone https://github.com/OWNER/REPO.git /opt/tahaqqaq
cd /opt/tahaqqaq
cp deploy/production.env.example .env.production
nano .env.production          # fill in every value
docker compose --env-file .env.production up -d --build
```

The first build takes 10 to 15 minutes. Database migrations run on every start of
the web container. When it finishes, open `https://YOUR_DOMAIN`.

Create the admin account once:

```bash
docker compose --env-file .env.production exec web python bootstrap_admin.py
```

## 3. Updating

```bash
cd /opt/tahaqqaq
git pull
docker compose --env-file .env.production up -d --build
```

## 4. Operating

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Web logs | `docker compose logs -f web` |
| Worker logs | `docker compose logs -f worker` |
| Restart | `docker compose --env-file .env.production restart web worker` |
| Database backup | `docker compose exec db pg_dump -U tahaqqaq tahaqqaq \| gzip > backup-$(date +%F).sql.gz` |
| Restore | `gunzip -c backup.sql.gz \| docker compose exec -T db psql -U tahaqqaq tahaqqaq` |

## 5. What runs

| Service | Role |
|---|---|
| `caddy` | HTTPS, reverse proxy, unbuffered progress streams |
| `web` | Flask + gunicorn (threads), serves the built React app and the API |
| `worker` | background jobs: origin searches, video analysis, indexing |
| `redis` | job queue and rate-limit storage |
| `db` | Postgres 16 with pgvector |

Uploads, the database, Redis data, certificates and the model cache live in Docker
volumes and survive rebuilds.

## 6. Notes

- Google Vision is optional: put the key file in `./secrets/` on the server and set
  `GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/google-credentials.json`.
- To build without the embedding model: `docker compose build --build-arg INSTALL_ML=false`
  and set `VISUAL_VERIFY=false`.
- `render.yaml`, `build.sh` and `Procfile` belong to the previous host and are not used here.
