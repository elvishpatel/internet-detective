# Internet Detective

**Don't just search. Investigate.** Internet Detective turns a public claim into a transparent case file: it creates multiple search angles, discovers publicly available sources, fetches accessible documents, extracts evidence, discounts duplicated reporting, looks for contradictions, and explains a heuristic verdict.

It is deliberately not an AI wrapper. The deterministic research/evidence engine remains the source of truth, and a **required AI review** checks the assembled evidence before a case can be marked complete. AI does not control the numeric score or gain web access.

## Features

- Background FastAPI investigations with a pollable status endpoint and mandatory AI verification before completion.
- Multi-angle no-key web discovery, optional public GitHub discovery, document fetching, extraction, URL/content deduplication, and SSRF protection.
- Evidence cards with original source links, supporting/contradicting/context classification, transparent authority and strength heuristics, contradictions, timeline, and interactive evidence graph.
- A distinct adversarial pass that searches for counter-evidence without pretending unreviewed search leads are proof.
- SQLite persistence, configurable research budgets, graceful failed-source handling, and three instant, clearly labelled demo cases.
- Responsive vanilla HTML/CSS/JavaScript frontend with no framework build step.

## Architecture

```text
Browser → FastAPI API → claim planner → public-source discovery → safe document fetcher
        → text extraction → deduplication → evidence / contradiction / score engine
        → SQLite case file → browser case board
```

The backend avoids access controls: it does not bypass authentication, CAPTCHAs, paywalls, or robots protections. It rejects localhost, private ranges, cloud metadata-style hosts, non-HTTP URLs, oversized pages, and userinfo URLs before fetching.

## Local setup (Windows)

1. Install [Python](https://www.python.org/downloads/) 3.11+ and verify it:

   ```bash
   python --version
   ```

2. Install [Git](https://git-scm.com/downloads) and verify it:

   ```bash
   git --version
   ```

3. Clone your repository and enter it:

   ```bash
   git clone YOUR_REPOSITORY_URL
   cd internet-detective
   ```

4. Create and activate an environment:

   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

   On macOS/Linux: `python3 -m venv venv` then `source venv/bin/activate`.

5. Install backend dependencies:

   ```bash
   pip install -r backend/requirements.txt
   ```

6. Copy `.env.example` to `.env` and configure a mandatory verifier. `FRONTEND_URL` is the permitted CORS origin; `DATABASE_PATH` is the local SQLite location; `MAX_*` values are per-case budgets. Do not commit `.env`.

7. Start the API (the database is initialized automatically):

   ```bash
   uvicorn backend.main:app --reload
   ```

   Expect Uvicorn to listen at `http://127.0.0.1:8000`; visit `/api/health` to confirm.

8. In a second terminal, serve the frontend:

   ```bash
   cd frontend
   python -m http.server 5500
   ```

   Open `http://localhost:5500` and try: `Did Tesla recently expand its operations?`

Run the focused logic tests with:

```bash
python -m unittest discover -s tests -v
```

## AI verification

Every live case asks a hosted model to review the assembled evidence before the case is presented. The AI never controls the numeric score and never gains web access; it only checks whether the verdict overstates the excerpts it was given.

### Why the verifier used to break

Hugging Face's router does not host models itself. It forwards each request to whichever third-party provider currently serves that repo, and those mappings change without notice. When Together AI retired the serverless build of `Qwen/Qwen2.5-7B-Instruct`, the router began answering `400 model_not_available`, and because the old code was pinned to that one model, no environment-variable value could bring it back.

The verifier is no longer pinned. On the first call it asks `https://router.huggingface.co/v1/models` which repos are live for your token, builds an ordered plan of `model:provider` attempts (smallest and cheapest first), and cascades through them until one answers. The winning combination is cached for later cases. If every seeded model disappears, it sweeps the live catalogue for a replacement instead of failing.

### Configuration

```text
REQUIRE_AI_VERIFICATION=true
AI_DEGRADE_GRACEFULLY=true
AI_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_your_secret_token
HUGGINGFACE_MODEL=
HUGGINGFACE_PROVIDER=auto
ENABLE_LOCAL_AI=false
```

Leave `HUGGINGFACE_MODEL` empty unless you want to force a specific model; the discovery pass is what keeps the service alive across provider changes. Create the token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) as a **fine-grained** token with the **Make calls to Inference Providers** permission, and add it to `.env` locally or to Render as a secret. Never put it in the frontend or commit it. Hugging Face's monthly experimentation credits are limited, so hosted verification is not permanently free at arbitrary traffic; [HF pricing](https://huggingface.co/docs/inference-providers/en/pricing) explains the credit model.

### Diagnosing it

Run this from the repository root before touching deployment settings:

```bash
python scripts/check_ai.py
```

It loads `.env`, lists how many models your token can reach, sends a real one-word request to each candidate until one answers, and prints the exact environment variables to paste into Render. It distinguishes the three failures that look identical from the outside: a token missing the inference permission, exhausted credits, and a model that simply moved off serverless.

On a deployed instance, `GET /api/health` reports the AI configuration without secrets, and `GET /api/health/ai` performs the same live probe and names the model that answered.

### Graceful degradation

With `AI_DEGRADE_GRACEFULLY=true` (the default), a total verifier outage no longer throws the investigation away. The case completes, and the AI review panel says plainly that the verdict was **not reviewed**, along with the reason. The deterministic research engine was always the source of truth, so losing the second pass should degrade the product rather than delete it. Set `AI_DEGRADE_GRACEFULLY=false` to restore the original hard-fail behaviour.

### Local model alternative

For no-per-call-cost local development, install [Ollama](https://ollama.com/), verify with `ollama --version`, then download a modest model:

```bash
ollama pull llama3.2:3b
```

Set the following in `.env` and restart the backend:

```text
REQUIRE_AI_VERIFICATION=true
AI_PROVIDER=ollama
ENABLE_LOCAL_AI=true
OLLAMA_URL=http://localhost:11434
```

The AI receives only the strongest supplied excerpts and is asked to flag unsupported inference; it never controls the main score. If Ollama is unreachable, the case degrades to a labelled unreviewed verdict (or hard-fails, if you set `AI_DEGRADE_GRACEFULLY=false`).

## Transparent scoring and source independence

Evidence strength is a visible heuristic based on source authority, relevance to claim terms, and directness of the sentence. The score adds bounded support, then adds a small bonus for unique reporting domains and subtracts contradicting evidence. It is **not a probability** or calibrated prediction.

Repeated URLs are normalized and dropped; identical extracted text is content-hashed and dropped. Independent confirmation is conservatively approximated from separate domains in this small-project version. That is a useful guardrail, but not a guarantee that newsrooms did not share an original report.

## Deploy

### Render backend

1. Push the repository to GitHub.
2. Create a Render account, choose **New → Blueprint**, and select `elvishpatel/internet-detective`. `render.yaml` supplies `pip install -r backend/requirements.txt` and `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
3. In the service’s Environment tab, enter `HUGGINGFACE_API_KEY` as a secret. Set `FRONTEND_URL` temporarily to your eventual Vercel domain, or update it after frontend deployment. Keep `ENABLE_LOCAL_AI=false`, `AI_PROVIDER=huggingface`, and `REQUIRE_AI_VERIFICATION=true`.
4. Deploy and verify `https://YOUR-RENDER-SERVICE/api/health`, then `https://YOUR-RENDER-SERVICE/api/health/ai` to confirm a model actually answers and see which one. Then start one investigation: it must complete with an `AI REVIEW: Hugging Face Inference Providers` footer, or an explicitly labelled unreviewed verdict.

Render’s ephemeral filesystem means the SQLite cache may reset after a redeploy or instance replacement. For a small public demo this is acceptable; use a persistent disk or managed database before relying on retention.

### Vercel / Netlify frontend

Deploy the `frontend` directory as a static site. Once Render has supplied your API URL, edit `frontend/config.js` and replace the empty value with it:

```js
window.API_BASE_URL = "https://YOUR-RENDER-SERVICE";
```

Commit that non-secret configuration value. In Vercel: **Add New → Project → Import** `elvishpatel/internet-detective`; set the Root Directory to `frontend`; Framework Preset to **Other**; leave build/output settings blank; then deploy.

Then deploy, test a demo case, a real claim, source links, error handling, and mobile layout. Set the same final frontend URL in Render’s `FRONTEND_URL` to enable CORS.

## GitHub first push

```bash
git init
git add .
git commit -m "Initial Internet Detective"
git branch -M main
git remote add origin https://github.com/elvishpatel/internet-detective.git
git push -u origin main
```

## Limitations and research honesty

Free public search endpoints may block, rate-limit, or change markup; a failed provider produces fewer sources, never fabricated ones. Hugging Face’s free credits and hosted-model availability can also limit a mandatory verifier. Search snippets are discovery leads, not evidence. Job posts, patents, domains, and repositories are signals—not proof of a launch or intent. Dates are only shown when extractable. The system may correctly return **Insufficient public evidence**, which means the retrieved public material did not establish the claim; it does not prove the opposite.
