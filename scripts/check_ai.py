"""Diagnose Hugging Face verification without redeploying anything.

Run it from the repository root:

    python scripts/check_ai.py

It loads .env (if present), asks the Hugging Face router which models your token
can actually serve, then sends a real one-token request to each candidate until
one answers. Finally it prints the exact environment variables to paste into
Render. Nothing is written to the database and no investigation is started.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_dotenv(path: Path) -> None:
    """Minimal .env loader so this script has no extra dependencies."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Must happen before backend.config is imported: settings are read at import time.
load_dotenv(ROOT / ".env")

import httpx  # noqa: E402

from backend.ai import huggingface as hf  # noqa: E402
from backend.config import settings  # noqa: E402

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = RED = DIM = BOLD = RESET = ""


async def main() -> int:
    key = settings.huggingface_api_key or os.environ.get("HUGGINGFACE_API_KEY", "")
    if not key:
        print(f"{RED}No HUGGINGFACE_API_KEY found.{RESET}")
        print("Put it in .env as HUGGINGFACE_API_KEY=hf_... or set it in your shell, then re-run.")
        print("Create one at https://huggingface.co/settings/tokens as a fine-grained token")
        print("with the 'Make calls to Inference Providers' permission.")
        return 2

    print(f"{BOLD}Internet Detective - AI verifier check{RESET}")
    print(f"token      : {key[:6]}...{key[-4:]} ({len(key)} chars)")
    print(f"model env  : {settings.huggingface_model or '(empty - auto-select)'}")
    print(f"provider   : {settings.huggingface_provider or '(empty - auto)'}")
    print()

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    messages = [{"role": "user", "content": "Reply with the single word: ready"}]

    async with httpx.AsyncClient(timeout=settings.huggingface_timeout) as client:
        print("Asking the router which models are live ...")
        try:
            response = await client.get(hf.MODELS_URL, headers=headers)
        except httpx.HTTPError as exc:
            print(f"{RED}Could not reach {hf.MODELS_URL}: {exc}{RESET}")
            return 2

        if response.status_code == 401:
            print(f"{RED}401 Unauthorized - the token is invalid or revoked.{RESET}")
            print("Create a new fine-grained token with 'Make calls to Inference Providers'.")
            return 2
        if response.status_code >= 400:
            print(f"{RED}{response.status_code} from the catalogue: {hf.terse(response.text)}{RESET}")
            print(f"{DIM}Continuing with blind cascading anyway.{RESET}")
            live: dict[str, list[str]] = {}
        else:
            live = await hf.catalog(client, headers, force=True)
            print(f"  {len(live)} model repos listed as live for this token.")

        attempts = hf.plan_attempts(live)
        print(f"\n{BOLD}Trying {len(attempts)} candidate(s), cheapest first:{RESET}")

        winner = None
        for model_id in attempts:
            print(f"  {model_id:<58} ", end="", flush=True)
            try:
                note = await hf.chat_once(client, headers, model_id, messages)
            except hf.AIConfigurationError as fatal:
                print(f"{RED}FATAL{RESET}")
                print(f"\n{RED}{fatal}{RESET}")
                return 2
            except Exception as exc:
                print(f"{RED}fail{RESET} {DIM}{exc}{RESET}")
                continue
            print(f"{GREEN}OK{RESET} {DIM}-> {note[:40]!r}{RESET}")
            winner = model_id
            break

    print()
    if not winner:
        print(f"{RED}No model answered.{RESET} Most likely causes, in order:")
        print("  1. The token lacks the 'Make calls to Inference Providers' permission.")
        print("  2. Your monthly inference credits are exhausted (check huggingface.co/settings/billing).")
        print("  3. Every candidate is gated and you have not accepted its licence on the model page.")
        print("\nWith AI_DEGRADE_GRACEFULLY=true the app still works - cases complete and are")
        print("clearly labelled as unreviewed rather than failing outright.")
        return 1

    base, _, provider = winner.partition(":")
    print(f"{GREEN}{BOLD}Working configuration found.{RESET} Set these on Render:\n")
    print(f"  HUGGINGFACE_MODEL={base}")
    print(f"  HUGGINGFACE_PROVIDER={provider or 'auto'}")
    print("  AI_PROVIDER=huggingface")
    print("  REQUIRE_AI_VERIFICATION=true")
    print("  AI_DEGRADE_GRACEFULLY=true")
    print(f"\n{DIM}You can also leave HUGGINGFACE_MODEL empty - the app rediscovers a live")
    print(f"model on its own, so it survives the next time a provider retires one.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
