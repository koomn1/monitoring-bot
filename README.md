# Quiz Space DevOps Bot

Telegram DevOps Bot for monitoring, deploying, and securing the Quiz Space
project — entirely on free-tier infrastructure. Full design docs in
[`docs/`](./docs) and [`modules/`](./modules).

## What's real vs. what's a stub

- **Real:** config loading, RBAC, command routing, inline-button confirm
  flows, audit-log middleware, scheduler, all 19 `/commands`, database
  migrations, GitHub Actions workflows, the webhook/health receiver.
- **Stubs (search for `TODO`):** backup storage target listing, exact
  `profiles` schema for Quiz Space's own users, Realtime websocket probe.

---

## 1. Push to GitHub

```bash
# from inside this folder — git is already initialized with one commit
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## 2. Deploy on Railway

1. On [railway.app](https://railway.app), **New Project → Deploy from GitHub repo** → select this repo.
   Railway auto-detects the `Dockerfile` and `railway.toml`.
2. Add environment variables under **Variables** (copy every key from
   [`.env.example`](./.env.example) — at minimum: `TELEGRAM_BOT_TOKEN`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OWNER_USER_IDS`,
   `WEBSITE_URL`, `API_BASE_URL`).
3. After the first deploy, Railway gives you a public domain
   (**Settings → Networking → Generate Domain**). Set that as
   `BOT_WEBHOOK_URL` back in your Railway variables (e.g.
   `https://your-app.up.railway.app`) — this is what GitHub Actions
   calls back to (see `.github/workflows/*.yml`).
4. Redeploy once after adding `BOT_WEBHOOK_URL` so it takes effect.

Railway health-checks `GET /health` (see `railway.toml`) — the Bot won't
be marked healthy until `TELEGRAM_BOT_TOKEN` + Supabase credentials are
valid (`settings.validate()` fails fast otherwise — check the deploy logs).

## 3. Run the database migrations

From your own machine (Railway's DB URL, not your app's runtime):

```bash
pip install -r requirements.txt
SUPABASE_DB_URL="postgresql://postgres:[password]@[host]:5432/postgres" \
    python scripts/run_migrations.py
```

Get `SUPABASE_DB_URL` from Supabase → **Project Settings → Database → Connection string**.

## 4. Wire up GitHub Actions secrets

In your GitHub repo → **Settings → Secrets and variables → Actions**, add:
`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_PROJECT_NAME`,
`SUPABASE_DB_URL`, `BOT_WEBHOOK_URL` (same Railway domain as above),
`GITHUB_WEBHOOK_SECRET` (any random string — put the same value in Railway's
`GITHUB_WEBHOOK_SECRET` variable too, so signatures verify).

## 5. Talk to your bot

Send `/start` in Telegram. If nothing responds, check Railway's **Deploy Logs**
first — `settings.validate()` prints exactly which variable is missing.

---

## Local development

```bash
cp .env.example .env      # fill in your values
pip install -r requirements.txt
python scripts/local_dev_runner.py
```

## Repo layout

See [`docs/02-project-structure.md`](./docs/02-project-structure.md) for the full breakdown.
