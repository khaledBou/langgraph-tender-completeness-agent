# Deployment on Scaleway

This guide deploys the Docker Compose stack of this repository on Scaleway. The stack itself was verified locally. The Scaleway steps follow the provider's documentation and were not executed as part of this repository: check each command against the current Scaleway console before running it.

## Target

- One Instance (DEV1-M is enough for a demonstration) running Docker, with the API and the interface from this repository.
- One Managed Database for PostgreSQL, so the checkpoints and the reviews survive the Instance.
- One reverse proxy on the Instance, Caddy, which obtains the TLS certificate.
- Files uploaded by users stay on the Instance volume. For a real deployment, move them to Object Storage.

## 1. Create the resources

In the Scaleway console, or with the CLI:

```bash
scw instance server create type=DEV1-M image=ubuntu_jammy name=tender zone=fr-par-1 ip=new
scw rdb instance create name=tender-db engine=PostgreSQL-16 node-type=DB-DEV-S user-name=tender password='<strong password>' region=fr-par
```

Open the inbound ports 22, 80 and 443 in the Instance security group. Note the public IP of the Instance and the endpoint of the database.

Point a DNS record of your domain to the Instance IP, for example `tender.example.com`.

## 2. Prepare the Instance

```bash
ssh root@<instance ip>
apt-get update && apt-get install -y git curl
curl -fsSL https://get.docker.com | sh
docker compose version   # 2.24 or later is required for the override below
git clone https://github.com/khaledBou/langgraph-tender-completeness-agent.git /opt/tender
cd /opt/tender
cp .env.example .env
```

Edit `.env`:

```
BACKEND_PORT=8010
FRONTEND_PORT=4210
ANTHROPIC_API_KEY=<your key>
DJANGO_SECRET_KEY=<long random string>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=tender.example.com,backend
CORS_ALLOWED_ORIGINS=https://tender.example.com
```

## 3. Use the managed database

Create `docker-compose.override.yml` so the backend uses the managed database instead of the local container:

```yaml
services:
  backend:
    environment:
      DATABASE_URL: postgres://tender:<password>@<db endpoint>:5432/rdb?sslmode=require
      CHECKPOINTER_URL: postgres://tender:<password>@<db endpoint>:5432/rdb?sslmode=require
    depends_on: !reset []
  db:
    profiles: ["local"]
```

The `!reset` tag removes the dependency on `db` declared in the base file (a plain `depends_on: []` would keep it). The `db` service is then only started with `--profile local`, which the production commands do not use. Check the merged configuration before starting anything:

```bash
docker compose config --quiet
```

## 4. Reverse proxy and TLS

Install Caddy on the Instance and give it this `/etc/caddy/Caddyfile`:

```
tender.example.com {
    reverse_proxy /api/* localhost:8010
    reverse_proxy localhost:4210
}
```

Caddy obtains and renews the certificate on its own. Reload it with `systemctl reload caddy`.

## 5. Start

```bash
cd /opt/tender
docker compose up --build -d backend frontend
docker compose logs -f backend
```

The entrypoint applies the migrations and loads the checklists. The interface is then available at `https://tender.example.com`.

## 6. Operate

- Update: `git pull && docker compose up --build -d backend frontend`.
- After a restart of the Instance, and before anyone creates a review, reconcile the reviews left running: `docker compose exec backend uv run python manage.py recover_reviews`.
- Logs: `docker compose logs -f`.
- Backups: enable the automatic backups of the Managed Database. The uploaded files live in the `media_data` Docker volume on the Instance.

## What this guide does not cover

- Authentication: the demonstration has no user accounts. Put the site behind your identity provider or a VPN before exposing real documents.
- Object Storage for the uploaded files.
- A worker process: the workflow runs in a thread of the API. For sustained load, move the execution to a task queue.
