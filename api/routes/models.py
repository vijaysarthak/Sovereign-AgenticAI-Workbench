"""Model inventory endpoint for the workbench's Models page.

ZERO ACCESS DECISIONS INSIDE.
Read-only: reports which local Ollama models this deployment is configured
to use (from the same env vars agents/real.py reads) and, best-effort,
whether each is actually pulled on the local Ollama server. Never leaves
the machine -- the only network call here is to OLLAMA_API_BASE, which is
local/LAN by this app's own air-gapped design (see agents/real.py).
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends
import httpx
from contracts import Principal
from auth.deps import current_principal

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("")
def list_models(
    principal: Principal = Depends(current_principal),
):
    """List the models this deployment is configured to use, labeled by role
    (primary drafting, fallback drafting, code, vision), plus whether each
    is actually installed on the local Ollama server right now."""
    backend = os.getenv("AGENT_BACKEND", "ollama").lower()
    ollama_api_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")

    configured = [
        {"id": os.getenv("OLLAMA_MODEL", "granite4.1:3b"), "role": "primary"},
        {"id": os.getenv("OLLAMA_FALLBACK_MODEL", "llama3.2:latest"), "role": "fallback"},
        {"id": os.getenv("OLLAMA_CODE_MODEL", "qwen2.5-coder:7b"), "role": "code"},
        {"id": os.getenv("OLLAMA_VISION_MODEL", "granite3.2-vision"), "role": "vision"},
    ]
    # De-duplicate by id (a deployment may reuse the same model for two roles),
    # keeping the first role each id was seen under and merging the rest.
    by_id: dict[str, dict] = {}
    for entry in configured:
        model_id = entry["id"]
        if not model_id:
            continue
        if model_id in by_id:
            by_id[model_id]["roles"].append(entry["role"])
        else:
            by_id[model_id] = {"id": model_id, "roles": [entry["role"]]}

    installed_ids: set[str] = set()
    installed_sizes: dict[str, int] = {}
    ollama_reachable = False
    if backend in ("ollama", "real"):
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{ollama_api_base}/api/tags")
                res.raise_for_status()
                ollama_reachable = True
                for m in res.json().get("models", []):
                    name = m.get("name") or m.get("model")
                    if name:
                        installed_ids.add(name)
                        installed_sizes[name] = m.get("size", 0)
        except Exception:
            pass  # best-effort only; status below just reflects "unknown"

    models = []
    for model_id, entry in by_id.items():
        if not ollama_reachable:
            status = "unknown"
        elif model_id in installed_ids:
            status = "installed"
        else:
            status = "missing"
        models.append({
            "id": model_id,
            "roles": entry["roles"],
            "status": status,
            "size_bytes": installed_sizes.get(model_id),
        })

    return {
        "backend": backend,
        "ollama_api_base": ollama_api_base,
        "ollama_reachable": ollama_reachable,
        "models": models,
    }
