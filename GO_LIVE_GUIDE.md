# Internet Detective — Complete Go-Live Guide

This is a click-by-click guide to take the project from your computer to a public URL,
using a **free Hugging Face model** for the mandatory AI verification, a **free Render**
backend, and a **free Vercel** frontend.

The whole thing is free to stand up. The only limited resource is Hugging Face's monthly
inference credit (explained in Step 1 and the FAQ).

---

## The big picture (read this once)

There are three moving parts:

```
[ Your browser ]  →  [ Vercel: frontend (static site) ]  →  [ Render: backend (FastAPI) ]  →  [ Hugging Face: AI verifier ]
```

1. **Hugging Face** gives you a secret token so the backend can call a free chat model.
2. **Render** runs your Python backend and holds that token as a secret env var.
3. **Vercel** hosts the HTML/JS frontend and is told the Render URL to call.

They connect through two settings you fill in at the end:
- The frontend needs to know the **backend URL** (`frontend/config.js`).
- The backend needs to allow the **frontend URL** for CORS (`FRONTEND_URL` on Render).

That circular dependency is normal — you deploy the backend first, get its URL, wire the
frontend, get *its* URL, then come back and set `FRONTEND_URL`.

---

## Step 0 — Prerequisites (5 min)

You need free accounts on:
- **GitHub** — your code is already at `github.com/elvishpatel/internet-detective`. ✅
- **Hugging Face** — https://huggingface.co/join
- **Render** — https://render.com (sign up with GitHub)
- **Vercel** — https://vercel.com (sign up with GitHub)

Signing up for Render and Vercel *with your GitHub account* is the smoothest path — it lets
them see your repo automatically.

---

## Step 1 — Get a free Hugging Face model token (5 min)

The backend does not run the model itself. It calls Hugging Face's hosted "Inference
Providers" API, which is OpenAI-compatible. You just need a token.

1. Log in at https://huggingface.co and go to **Settings → Access Tokens**
   (direct link: https://huggingface.co/settings/tokens).
2. Click **Create new token** and choose the **Fine-grained** type.
3. Give it a name like `internet-detective`.
4. Under permissions, tick **"Make calls to Inference Providers"**.
   (This is the only permission it needs. Don't grant write/repo scopes.)
5. Click **Create token** and **copy it now** — it looks like `hf_xxxxxxxxxxxxxxxx`.
   You won't be able to see it again; if you lose it, delete and make a new one.

Keep this token secret. It goes into Render as an environment variable — **never** into
`frontend/config.js`, never committed to GitHub.

### Which model? (and the free-credit reality)

The project defaults to `google/gemma-2-2b-it:fastest`, a small, fast, free-tier-friendly
instruct model. The `:fastest` suffix just lets Hugging Face pick the quickest provider.

Hugging Face gives every account a **small monthly credit** for Inference Providers. For a
demo and light personal use this is effectively free. It is **not** unlimited — if you run
many investigations and exhaust the credit, verification calls start failing, and because
this app *requires* AI verification, those cases will end with a clear "verification failed"
message rather than a fake verdict. That is by design.

If you ever want zero per-call cost, the local Ollama option is documented in the README —
but Ollama can't run on Render's free tier, so for a *public* site Hugging Face is the path.

---

## Step 2 — (Optional but recommended) Test the model locally first (10 min)

This proves your token works before you deal with deployment. Skip to Step 3 if you're
confident.

1. In the project folder, copy `.env.example` to `.env`:
   ```bash
   copy .env.example .env      REM Windows
   ```
2. Open `.env` and paste your token:
   ```
   HUGGINGFACE_API_KEY=hf_your_secret_token
   ```
3. Create a virtual environment and install deps:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```
4. Run the backend:
   ```bash
   uvicorn backend.main:app --reload
   ```
5. Open http://127.0.0.1:8000/api/health — you should get a healthy JSON response.
6. In a second terminal, serve the frontend:
   ```bash
   cd frontend
   python -m http.server 5500
   ```
7. Open http://localhost:5500 and run: `Did Tesla recently expand its operations?`
   If the case completes with an "AI REVIEW: Hugging Face Inference Providers" footer, your
   token and model work. If it fails with a verification error, the token or model name is
   the problem — fix that here, before deploying.

> If the model name is ever rejected (Hugging Face occasionally retires models), pick another
> small instruct model from https://huggingface.co/models?inference_provider=all&pipeline_tag=text-generation
> and set `HUGGINGFACE_MODEL` to its `id`. Good small alternatives to try:
> `meta-llama/Llama-3.2-3B-Instruct`, `Qwen/Qwen2.5-3B-Instruct`.

---

## Step 3 — Deploy the backend to Render as a Web Service (10 min)

> **Why not Blueprint?** The Blueprint flow (`render.yaml`) sometimes asks for card details
> up front. Creating a plain **Web Service** manually stays on the **free tier with no card
> required**. Your project works exactly the same either way — you just type in the two
> commands and the env vars yourself instead of letting `render.yaml` do it. You can leave
> `render.yaml` in the repo; it's simply ignored by this path.

1. Go to https://dashboard.render.com and click **New → Web Service**.
2. Choose **Build and deploy from a Git repository** and connect GitHub if prompted.
3. Pick **`elvishpatel/internet-detective`**.
4. Fill in the settings form:
   - **Name:** `internet-detective-api` (or anything)
   - **Region:** whichever is closest to you
   - **Branch:** `main`
   - **Root Directory:** leave **blank** (the commands below already point into `backend/`)
   - **Runtime / Language:** **Python 3**
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** select **Free**. (This is the step that avoids the card — make sure
     "Free" is chosen, not a paid plan.)
5. Expand **Advanced → Environment Variables** (or add them after creation in the
   **Environment** tab) and add these one by one. These are the same values `render.yaml`
   would have set — you're just entering them manually:

   | Key | Value |
   |---|---|
   | `HUGGINGFACE_API_KEY` | your `hf_...` token (secret) |
   | `AI_PROVIDER` | `huggingface` |
   | `REQUIRE_AI_VERIFICATION` | `true` |
   | `ENABLE_LOCAL_AI` | `false` |
   | `HUGGINGFACE_MODEL` | `Qwen/Qwen2.5-7B-Instruct` |
   | `HUGGINGFACE_PROVIDER` | `together` (or `auto`) |
   | `DATABASE_PATH` | `./data/investigator.db` |
   | `FRONTEND_URL` | `*` for now — you'll set the real Vercel URL in Step 5 |

6. Click **Create Web Service** and wait for the build to finish (a few minutes). Watch the
   log; it should end with Uvicorn starting up.
7. You'll get a URL like `https://internet-detective-api.onrender.com`.
   **Copy it.** Visit `https://internet-detective-api.onrender.com/api/health` — you should
   see a healthy response.

> If Render *still* asks for a card even with the Free instance selected, it's usually
> because a card is required once per account for verification (it isn't charged on free
> services). But you can avoid it entirely by using a free alternative host — see
> **Appendix A** below for Railway / Fly.io / Hugging Face Spaces options.

> **Free-tier note:** Render's free web services **sleep after ~15 min of inactivity** and
> take ~30–60s to wake on the next request. The first investigation after a nap will feel
> slow — that's the cold start, not a bug.
>
> **Data note:** Render's free filesystem is ephemeral, so the SQLite case history resets on
> redeploys/restarts. Fine for a demo. For persistent history, add a Render persistent disk
> or a managed database later.

---

## Step 4 — Deploy the frontend to Vercel (10 min)

The frontend is plain HTML/CSS/JS with no build step — Vercel just serves the `frontend`
folder.

**First, point the frontend at your backend.** Edit `frontend/config.js` on your computer:

```js
window.API_BASE_URL = "https://internet-detective-api.onrender.com";
```

Use *your* Render URL, with **no trailing slash**. This value is not secret — commit it:

```bash
git add frontend/config.js
git commit -m "Point frontend at Render backend"
git push
```

Then deploy:

1. Go to https://vercel.com/new and **Import** `elvishpatel/internet-detective`.
2. Set **Root Directory** to `frontend`.
3. Set **Framework Preset** to **Other**.
4. Leave Build Command and Output Directory **blank** (it's a static site).
5. Click **Deploy**. You'll get a URL like `https://internet-detective.vercel.app`.
   **Copy it.**

---

## Step 5 — Connect the two (close the CORS loop) (5 min)

The backend only accepts browser requests from origins listed in `FRONTEND_URL`.

1. Back in Render → your service → **Environment**, set:
   ```
   FRONTEND_URL=https://internet-detective.vercel.app
   ```
   (your real Vercel URL, no trailing slash). You can list several comma-separated origins if
   you also want localhost, e.g.
   `https://internet-detective.vercel.app,http://localhost:5500`.
2. Save — Render redeploys automatically.

---

## Step 6 — Final verification checklist

Open your Vercel URL and confirm each of these:

- [ ] A **demo case** loads instantly (the three labelled demos).
- [ ] A **real claim** (e.g. *"Did Tesla recently expand its operations?"*) runs and
      completes with an **"AI REVIEW: Hugging Face Inference Providers"** footer.
- [ ] **Source links** open the original pages.
- [ ] An intentionally weak claim returns **"Insufficient public evidence"** gracefully
      (not a crash).
- [ ] The layout works on **mobile** (resize the window).
- [ ] Browser console (F12) shows **no CORS errors**. If you see one, `FRONTEND_URL` on
      Render doesn't exactly match your Vercel origin.

If all six pass, you are live. 🎉

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| CORS error in console | `FRONTEND_URL` ≠ Vercel origin | Match it exactly, no trailing slash, redeploy Render |
| Every case fails "AI verification failed" | Bad/missing token, exhausted HF credit, or retired model | Re-check `HUGGINGFACE_API_KEY`; try another model id; check HF usage |
| First request very slow | Render free-tier cold start | Normal; wait ~60s or upgrade tier |
| Frontend calls `localhost:8000` | `config.js` still empty | Set `window.API_BASE_URL` to the Render URL and redeploy Vercel |
| Case history disappears | Render ephemeral disk | Expected on free tier; add persistent disk/DB for retention |
| 404 on the site | Vercel Root Directory not set to `frontend` | Set it in Project Settings → General |

---

## Cost summary

- **Hugging Face:** free monthly Inference Providers credit; enough for demos/light use.
  Heavy traffic can exhaust it, after which verification (and thus new cases) fails cleanly.
- **Render:** free web tier (sleeps when idle, ephemeral storage).
- **Vercel:** free hobby tier for the static frontend.

Total to go live: **$0**. Scaling beyond light demo use is where you'd start paying.

---

## Appendix A — Card-free backend hosts (if Render insists on a card)

Render usually asks for a card **once per account** for verification and does not charge free
services, but if you'd rather not enter one at all, these hosts run the same FastAPI backend.
The only thing that changes is where the backend lives — you still put your Render/host URL
into `frontend/config.js` (Step 4) and set `FRONTEND_URL` on the host (Step 5).

### Option 1 — Hugging Face Spaces (no card, same account you already made)

Since you already have a Hugging Face account, this is the least friction. Spaces can run a
Docker container for free.

1. Add a `Dockerfile` at the repo root (I can generate this for you — just ask):
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY . .
   RUN pip install --no-cache-dir -r backend/requirements.txt
   ENV PORT=7860
   CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
   ```
2. Create a new **Space** → SDK: **Docker** → link your GitHub repo (or push to the Space).
3. In the Space **Settings → Variables and secrets**, add the same env vars from Step 3
   (`HUGGINGFACE_API_KEY` as a *secret*, the rest as variables). Spaces expose port `7860`.
4. Your backend URL becomes `https://<user>-<space>.hf.space`.

Note: free Spaces also sleep when idle, same as Render.

### Option 2 — Railway (free trial credit, no card to start)

1. https://railway.app → **New Project → Deploy from GitHub repo** → pick the repo.
2. Set **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   and **Build**: it auto-detects Python and runs `pip install -r backend/requirements.txt`
   (add a root `requirements.txt` pointing to backend, or set the build command explicitly).
3. Add the same environment variables. Railway gives you a public domain under **Settings →
   Networking → Generate Domain**.

### Option 3 — Fly.io (no card for small free allowance)

Requires the `flyctl` CLI and a `fly.toml` + `Dockerfile`. More setup than the above; use it
only if you're comfortable with a CLI. Ask me and I'll generate the config files.

**Recommendation:** try Render's Free Web Service first (Step 3). If it demands a card you
don't want to give, **Hugging Face Spaces (Option 1)** is the cleanest fallback since you're
already on Hugging Face. I can write the `Dockerfile` for you whenever you want.
