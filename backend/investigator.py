import asyncio
import hashlib
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
from backend.config import settings
from backend.database import db
from backend.extraction.claims import decompose, build_queries
from backend.extraction.document_parser import extract_html
from backend.search import web, github
from backend.utils.urls import normalize_url, is_safe_public_url
from backend.analysis.evidence import evidence_from_document
from backend.analysis.scoring import score
from backend.analysis.graph import build as build_graph
from backend.analysis.contradictions import find as find_contradictions
from backend.ai.ollama import OllamaProvider
from backend.ai.huggingface import HuggingFaceProvider, AIUnavailableError

HEADERS = {"User-Agent": "InternetDetective/1.0 (+respectful public research)"}


def _unverified(exc: Exception) -> dict:
    """A case the AI never reviewed, labelled so nobody mistakes it for a verified one."""
    return {
        "available": False,
        "required": settings.require_ai_verification,
        "degraded": True,
        "provider": "AI verification unavailable",
        "model": "not reviewed",
        "note": (
            "This case was NOT reviewed by the AI verifier. The deterministic evidence engine "
            "produced the verdict and every source link is unchanged, but no second pass checked "
            "whether the conclusion overstates the evidence. Treat it as unreviewed. Reason: "
            + str(exc)[:500]
        ),
    }


async def _verify(claim: str, evidence: list, scoring: dict) -> dict:
    """Run the AI review, degrading to a labelled 'unreviewed' result when configured to."""
    try:
        if settings.ai_provider == "ollama":
            if not settings.enable_local_ai:
                raise AIUnavailableError("AI_PROVIDER is ollama but ENABLE_LOCAL_AI is false.")
            provider = OllamaProvider()
        elif settings.ai_provider == "huggingface":
            provider = HuggingFaceProvider()
        else:
            raise AIUnavailableError("AI_PROVIDER must be 'huggingface' or 'ollama'.")
        ai = await provider.review_conclusion(claim, evidence, scoring)
        ai.setdefault("provider", provider.name)
        ai.setdefault("degraded", False)
        ai["required"] = settings.require_ai_verification
        return ai
    except Exception as exc:
        if settings.require_ai_verification and not settings.ai_degrade_gracefully:
            raise AIUnavailableError(str(exc)) from exc
        return _unverified(exc)


async def run(case_id: str, claim: str, mode: str):
    try:
        # Only refuse to open a case up-front when a missing verifier is fatal. With
        # AI_DEGRADE_GRACEFULLY on, the research still has value, so we run the case
        # and label the missing review honestly at the end instead.
        if settings.require_ai_verification and not settings.ai_degrade_gracefully:
            if settings.ai_provider == "huggingface" and not settings.huggingface_api_key:
                raise AIUnavailableError("AI verification is required. Configure HUGGINGFACE_API_KEY before opening a case.")
            if settings.ai_provider == "ollama" and not settings.enable_local_ai:
                raise AIUnavailableError("AI verification is required. Set ENABLE_LOCAL_AI=true or use AI_PROVIDER=huggingface.")
        db.update_status(case_id, "researching", "Decomposing claim and creating investigation plan")
        parts = decompose(claim)
        queries = build_queries(claim, parts, settings.max_queries)
        db.record(case_id, "search_queries", [(case_id, q, datetime.now(timezone.utc).isoformat()) for q in queries])

        db.update_status(case_id, "researching", "Discovering public sources across search angles")
        batches = await asyncio.gather(*[web.discover(q, 7) for q in queries[:min(10, len(queries))]], return_exceptions=True)
        found = []
        for batch in batches:
            if isinstance(batch, list): found.extend(batch)
        # GitHub is a separate, openly accessible source family; it is a signal, never proof.
        if mode == "deep": found.extend(await github.discover(parts["subject"], 4))
        unique = OrderedDict()
        for item in found:
            clean = normalize_url(item.url)
            if clean not in unique: unique[clean] = item.json() | {"url": clean}
        sources = list(unique.values())[:settings.max_urls]
        db.record(case_id, "sources", [(case_id, x["url"], x["title"], x["domain"], x["source_type"], x["snippet"], x["published_at"], x["domain"]) for x in sources])

        db.update_status(case_id, "researching", f"Fetching and extracting {min(len(sources), settings.max_documents)} public documents")
        documents = await _fetch_documents(sources[:settings.max_documents])
        seen_hashes, evidence, timeline = set(), [], []
        for source, document in documents:
            digest = hashlib.sha256(document["text"].lower().encode()).hexdigest()
            if digest in seen_hashes: continue
            seen_hashes.add(digest)
            source["title"] = document["title"] or source["title"]
            items = evidence_from_document(claim, source, document["text"])
            evidence.extend(items)
            if items: timeline.append({"date": "Undated public record", "title": source["title"], "url": source["url"], "stance": items[0]["stance"]})

        db.update_status(case_id, "analyzing", "Testing evidence independence and contradictions")
        # Preserve a small, legible case board rather than flooding the UI with weak snippets.
        evidence.sort(key=lambda x: (x["stance"] == "supporting", x["strength"]), reverse=True)
        evidence = evidence[:18]
        scoring = score(evidence, len(sources))
        contradictions = find_contradictions(evidence)
        db.update_status(case_id, "verifying", "Running AI evidence verification")
        ai = await _verify(claim, evidence, scoring)
        result = {
            "id": case_id, "claim": claim, "mode": mode, "decomposition": parts, "plan": ["Official and primary evidence", "Public reporting", "Hiring, technical, and regulatory signals", "Contradicting evidence and alternative explanations"],
            "queries": queries, "stats": {"discovered": len(found), "usable": len(sources), "duplicates": max(0, len(found)-len(sources)), "documents": len(documents), "independent_chains": scoring["independent_chains"]},
            "evidence": evidence, "timeline": timeline[:12], "graph": build_graph(claim, evidence), "contradictions": contradictions,
            "score": scoring, "unknowns": ["No direct official confirmation was found in the retrieved public material.", "Absence of a public record is not evidence that an event will not occur.", "Some sources may be incomplete, inaccessible, or published after this investigation."],
            "ai_review": ai, "method_note": "Sources were discovered through public search results, fetched individually where accessible, deduplicated by normalized URL and content hash, then scored with visible heuristic weights. " + ("The AI evidence review could not run for this case, so the verdict below is unreviewed." if ai.get("degraded") else "The case was completed after a successful AI evidence review.") + " Search snippets are never treated as proof."
        }
        db.record(case_id, "evidence", [(case_id, x["source_url"], x["stance"], x["strength"], x["excerpt"], x["reasoning"]) for x in evidence])
        db.save_result(case_id, result)
    except Exception as exc:
        db.update_status(case_id, "failed", "Investigation halted safely", str(exc))


async def challenge(case_id: str):
    case = db.get_case(case_id)
    if not case or not case.get("result"): return None
    result = case["result"]
    # A transparent adversarial pass: expands negative-search angles, then reports actual returned material.
    queries = [result["claim"] + " denied", result["claim"] + " cancelled", result["decomposition"]["subject"] + " no plans"]
    batches = await asyncio.gather(*[web.discover(q, 5) for q in queries], return_exceptions=True)
    leads = [x.json() for batch in batches if isinstance(batch, list) for x in batch][:10]
    result["challenge"] = {"status": "complete", "queries": queries, "leads": leads, "note": "Adversarial search completed. Leads are not treated as evidence unless their underlying pages are retrieved and assessed in a new investigation."}
    db.save_result(case_id, result)
    return result


async def _fetch_documents(sources):
    async def fetch(source):
        if not is_safe_public_url(source["url"]): return None
        try:
            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=10) as client:
                response = await client.get(source["url"])
                if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""): return None
                if len(response.content) > 2_500_000: return None
                return source, extract_html(response.text, source["url"])
        except Exception: return None
    results = await asyncio.gather(*[fetch(x) for x in sources])
    return [x for x in results if x and len(x[1]["text"]) > 220]
