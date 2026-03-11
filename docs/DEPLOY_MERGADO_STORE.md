# Deploy for Mergado Store (GitHub + Render)

To use this app as a **Mergado Store extension**, it must be reachable at a **public URL**. Running on `localhost` only works on your machine; when users open the extension from [store.mergado.com](https://store.mergado.com/), Mergado needs to load your app from the internet.

This guide walks through **GitHub + Render** so you get a URL like `https://mergado-shopify-connector.onrender.com`.

## Why GitHub + Render?

- **Render** gives you a public HTTPS URL and runs the app 24/7.
- **GitHub** holds your code; Render can auto-deploy on every push to `main`.
- The project already includes a **render.yaml** blueprint so Render can create the web service and database from the repo.

## 1. Push code to GitHub

If the project is not in a GitHub repo yet:

```bash
cd /path/to/Shopify_connector-main
git init
git add .
git commit -m "Initial commit - Shopify Import & Sync"
# Create a new repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

Use your actual GitHub username and repo name.

## 2. Create a Render account and connect GitHub

1. Go to [render.com](https://render.com) and sign up (or log in).
2. In the dashboard, go to **Account Settings** → **Integrations** and connect your **GitHub** account.
3. Grant Render access to the repository that contains this project.

## 3. Create the Web Service and Database from the blueprint

1. In the Render dashboard, click **New** → **Blueprint**.
2. Connect the GitHub repo that contains this project.
3. Render will detect **render.yaml** in the repo. Select the repo and branch (e.g. `main`).
4. Render will propose:
   - A **Web Service** (Python, using `buildCommand` and `startCommand` from render.yaml).
   - A **PostgreSQL** database.
5. Click **Apply** to create both. Render will assign a URL like `https://mergado-shopify-connector.onrender.com` (the exact name comes from `name` in render.yaml).

## 4. Set environment variables

In the Render dashboard, open your **Web Service** → **Environment** and set:

| Key | Value |
|-----|--------|
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `false` |
| `FLASK_SECRET_KEY` | Generate a long random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `MERGADO_CLIENT_ID` | From your Mergado app (developer/OAuth settings) |
| `MERGADO_CLIENT_SECRET` | From your Mergado app |
| `MERGADO_REDIRECT_URI` | `https://<YOUR-RENDER-URL>/auth/callback` (see below) |
| `LOG_LEVEL` | `INFO` |
| `LOG_FORMAT` | `json` |

**Important:** Replace `<YOUR-RENDER-URL>` with the actual URL Render gave your service (e.g. `https://mergado-shopify-connector.onrender.com`). So the full redirect URI is:

```text
https://mergado-shopify-connector.onrender.com/auth/callback
```

`DATABASE_URL` is usually set automatically by Render when you link the PostgreSQL database to the web service. If you created them with the same blueprint, the link is often already there.

## 5. Run database migrations

Render does not run Flask-Migrate for you. After the first deploy:

1. Open your Web Service in Render.
2. Open the **Shell** tab (or use **Background Workers** if you add a migration job).
3. In the shell, run:

```bash
export FLASK_APP=main.py
flask db upgrade
```

If `FLASK_APP` is already set in the service environment, you can run:

```bash
flask db upgrade
```

## 6. Configure the app in Mergado

In the **Mergado** developer / app settings (where you created the OAuth app):

1. **Redirect URI**  
   Add exactly:
   ```text
   https://mergado-shopify-connector.onrender.com/auth/callback
   ```
   (again, use your real Render URL). This must match `MERGADO_REDIRECT_URI` in Render.

2. **Extension / App URL**  
   Set the URL where the extension should open (e.g. the root of your app):
   ```text
   https://mergado-shopify-connector.onrender.com
   ```
   So when a user opens your extension from the Mergado Store, Mergado sends them to this URL.

Save the Mergado app settings.

## 7. Open the extension from the Mergado Store

1. Deploy (or redeploy) the service on Render so the latest code and env are active.
2. In Mergado, add or publish your extension so it appears in the [Mergado Store](https://store.mergado.com/).
3. Open the extension from the Store. You should be sent to your Render URL, then through login and back to your app after OAuth.

## 8. Optional: custom subdomain

In Render, you can add a **custom domain** (e.g. `shopify-connector.yourdomain.com`) in the service settings. If you do, use that URL everywhere instead of `*.onrender.com` (redirect URI and Mergado app URL).

## Troubleshooting

- **Redirect to store.mergado.com after login**  
  Usually means the **redirect URI** in Mergado does not exactly match `MERGADO_REDIRECT_URI` (including `https`, host, and `/auth/callback`). Fix both and redeploy/restart.

- **500 from app.mergado.com**  
  Often the same redirect URI mismatch. Double-check Mergado app settings and Render env.

- **Database errors on Render**  
  Ensure the PostgreSQL service is created and linked to the web service, and that `DATABASE_URL` is set. Run `flask db upgrade` from the Render shell.

- **Service sleeps (free tier)**  
  On the free plan, the service may spin down after inactivity. The first request after that can be slow; consider the paid plan if you need always-on.

---

**Summary:** Push code to GitHub → Connect repo to Render → Create Web Service + PostgreSQL from render.yaml → Set env (especially `MERGADO_REDIRECT_URI` with your Render URL + `/auth/callback`) → Run `flask db upgrade` in Render shell → Set redirect URI and app URL in Mergado → Open extension from the Mergado Store.
