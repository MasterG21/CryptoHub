# Deploying the PawConnect backend

The iOS app talks to this API over HTTPS — it can't reach `localhost` on your
laptop, and Apple's App Transport Security blocks plain HTTP in a release
build. Before you archive the app for TestFlight/App Store, the backend needs
to be running somewhere public with a real TLS certificate.

A `Dockerfile` is included so any container host works. Below are the
straightforward options; pick whichever you're already comfortable with.
None of this can be done for you by an AI session — it requires an account
(and payment method, on paid tiers) that belongs to you.

## Option A: Render.com (simplest, has a free tier)

1. Push this repo to GitHub (already done if you're reading this from the
   branch).
2. In the Render dashboard: **New > Web Service**, connect the repo.
3. Set:
   - **Root directory**: `pet_sitter_app`
   - **Runtime**: Docker (Render will pick up the `Dockerfile` automatically)
4. Add an environment variable `PET_SITTER_SECRET_KEY` — generate one with:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```
   Without this, JWTs stop working every time the service restarts.
5. Free/starter plans have **ephemeral disks** — the SQLite file is wiped on
   every deploy or restart. For anything beyond a quick demo, add a Render
   **persistent disk** mounted at `/data` (matches the Dockerfile's default
   `PET_SITTER_DB_URL=sqlite:////data/pet_sitter.db`), or switch to a managed
   Postgres instance (see below).
6. Deploy. Render gives you an HTTPS URL like `https://pawconnect-api.onrender.com`
   — that's what goes into the iOS build config (see below).

## Option B: Fly.io

```bash
cd pet_sitter_app
fly launch          # detects the Dockerfile; say no to a Postgres DB unless you want one
fly volumes create pawconnect_data --size 1   # persistent volume for SQLite
fly secrets set PET_SITTER_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
fly deploy
```
Mount the volume at `/data` in `fly.toml` (fly.io's generated config) so it
matches the Dockerfile's `PET_SITTER_DB_URL`.

## Option C: Railway.app

Connect the repo, set the root directory to `pet_sitter_app`, Railway
detects the Dockerfile automatically. Add `PET_SITTER_SECRET_KEY` under
Variables. Railway's volumes work the same way — attach one at `/data` for
persistence, or add a Railway Postgres plugin.

## Option D: Your own VPS with Docker

```bash
cd pet_sitter_app
docker build -t pawconnect-api .
docker run -d --name pawconnect-api \
  -p 8000:8000 \
  -v pawconnect_data:/data \
  -e PET_SITTER_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
  --restart unless-stopped \
  pawconnect-api
```
Put this behind a reverse proxy (Caddy is the least fuss — it gets you a
free, auto-renewing Let's Encrypt certificate with a two-line Caddyfile) so
the app is reachable over HTTPS on your domain.

## Moving off SQLite for real production traffic

SQLite-on-a-volume is fine for testing and a small number of concurrent
users. For a real launch, point `PET_SITTER_DB_URL` at a managed Postgres
instance instead (all three hosts above offer one):

```
PET_SITTER_DB_URL=postgresql+psycopg2://user:password@host:5432/pawconnect
```

You'll need to add `psycopg2-binary` to `requirements.txt` — the
SQLAlchemy models don't change at all.

## Wiring the deployed URL into the iOS app

Once you have a public HTTPS URL, set it in
`pet_sitter_app/ios/PawConnect/project.yml` under `settings.base.API_BASE_URL`,
then re-run `xcodegen generate` (see `pet_sitter_app/ios/PawConnect/README.md`).
You can also override it per-scheme in Xcode's build settings if you want
separate staging/production backends.

## CORS

`app/main.py` already allows all origins (`allow_origins=["*"]`) — this
matters for the web frontend in a browser; a native iOS app calling the API
via `URLSession` isn't subject to CORS at all, so no extra configuration is
needed for the mobile client.
