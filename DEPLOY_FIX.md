# Redeploy guide — fixing the AI verifier

Follow these in order. Total time: about 10 minutes, most of it waiting on Render.

---

## Step 1 — Test locally first (2 minutes)

Do this **before** pushing anything. It tells you whether your Hugging Face token
works, so you don't debug a deployment when the real problem is the token.

Open PowerShell in the project folder:

```powershell
cd E:\Programmes\internet-detective
```

If you don't have a `.env` file locally, set the key just for this window:

```powershell
$env:HUGGINGFACE_API_KEY="hf_your_actual_token_here"
```

Then run:

```powershell
python scripts/check_ai.py
```

**What you want to see:**

```
Working configuration found. Set these on Render:

  HUGGINGFACE_MODEL=Qwen/Qwen3-8B
  HUGGINGFACE_PROVIDER=auto
  ...
```

If you see that, your token is fine — go to Step 2.

If it says `FATAL` or `No model answered`, stop and read the "If it still fails"
section at the bottom. Pushing code won't help until that's resolved.

---

## Step 2 — Push the fixed code (1 minute)

```powershell
cd E:\Programmes\internet-detective
git add -A
git commit -m "Fix AI verifier: unpin model, add router discovery and graceful degradation"
git push
```

This triggers **both** deployments automatically:

- Render rebuilds the backend (the actual fix)
- Vercel rebuilds the frontend (it needs the new "AI review unavailable" label)

---

## Step 3 — Fix the environment variables on Render (3 minutes)

Go to your Render dashboard → your `internet-detective-api` service →
**Environment** in the left sidebar.

Make the variables match this list exactly:

| Variable | Value | Note |
|---|---|---|
| `HUGGINGFACE_API_KEY` | `hf_your_token` | keep what you have |
| `HUGGINGFACE_MODEL` | *(leave completely empty)* | **this is the important one** |
| `HUGGINGFACE_PROVIDER` | `auto` | |
| `AI_DEGRADE_GRACEFULLY` | `true` | add this — it's new |
| `AI_PROVIDER` | `huggingface` | |
| `REQUIRE_AI_VERIFICATION` | `true` | |
| `ENABLE_LOCAL_AI` | `false` | |
| `FRONTEND_URL` | your Vercel URL | e.g. `https://internet-detective.vercel.app` |

**The single most important change:** clear out `HUGGINGFACE_MODEL`. Delete
`Qwen/Qwen2.5-7B-Instruct` and leave the box blank, or delete the whole variable.
An empty value is what tells the app to go find a model that actually works. If
you leave the dead model pinned there, it will keep being tried first.

`FRONTEND_URL` must be your Vercel URL with **no trailing slash**, or the browser
will block the API calls with a CORS error.

Click **Save Changes**. Render restarts the service on its own.

---

## Step 4 — Confirm it's actually working (2 minutes)

Wait for the deploy to finish (Render shows a green **Live**), then open these two
URLs in your browser. Replace `YOUR-SERVICE` with your real Render subdomain.

**First:**

```
https://YOUR-SERVICE.onrender.com/api/health
```

You should get something like:

```json
{"status":"ok","service":"internet-detective",
 "ai":{"provider":"huggingface","key_configured":true,"model":"auto", ...}}
```

Check that `key_configured` is `true` and `model` is `auto`. If you get a plain
`{"status":"ok","service":"internet-detective","ai":"optional"}` instead, Render
is still running the old code — go to **Manual Deploy → Deploy latest commit**.

**Then the real test:**

```
https://YOUR-SERVICE.onrender.com/api/health/ai
```

This sends a live request to Hugging Face. You want:

```json
{"ok":true,"model":"Qwen/Qwen3-8B:novita","catalogue_size":184,"skipped":[]}
```

`"ok":true` means the verifier is working. The `model` field tells you which one
it picked, and `skipped` shows what it tried and rejected on the way — that list
is your debugging trail if anything looks off.

**Note on the free tier:** Render spins your service down when idle, so the very
first request after a quiet period can take 50+ seconds. That's normal, not a
failure. Just wait for it.

---

## Step 5 — Run a real case

Open your Vercel frontend and investigate something, for example:

> Did Tesla recently expand its operations?

At the bottom of the case board, the panel should say **Required AI review ·
{model name}** with a short review paragraph.

If it says **⚠ AI review unavailable** instead, the case still completed and all
your evidence and sources are intact — the panel just tells you the second-pass
review didn't run, and gives the reason. That's the graceful degradation working
as intended, not a crash.

---

## If it still fails

Read the actual message from `/api/health/ai` — it now names the cause instead of
hiding it.

**`"fatal":true` and it mentions permissions or 401**

Your token is the problem. Go to
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) and
create a **Fine-grained** token (not a Read token). Scroll down and tick
**Make calls to Inference Providers**. This checkbox is the single most common
cause of this failure. Copy the new token into Render and save.

**It mentions credits, quota, or "exceeded"**

Your free monthly Hugging Face inference credits are used up. Check
[huggingface.co/settings/billing](https://huggingface.co/settings/billing). They
reset monthly. Until then the app still works with the "not reviewed" label,
since `AI_DEGRADE_GRACEFULLY=true`.

**`"ok":false` with a long `tried` list, no fatal flag**

Genuinely unusual — it means several different models were all unavailable. Run
`python scripts/check_ai.py` locally with the same token; it prints the same
diagnosis with more detail and costs nothing.

**404 on `/api/health/ai`**

Old code is still live. In Render: **Manual Deploy → Clear build cache & deploy**.

**Browser console shows a CORS error**

`FRONTEND_URL` on Render doesn't exactly match your Vercel domain. No trailing
slash, and `https://` included.

---

## Why this won't break again

The old code named one model and died when its provider retired it. The new code
asks Hugging Face which models are live for your token every 15 minutes, tries
them cheapest-first, and remembers the winner. Failed attempts cost no credits —
only the successful one does. When a provider retires a model next time, the app
picks a different one on the next case instead of going down.
