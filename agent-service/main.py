from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import uuid
import time
import json
import hashlib
import httpx
from pathlib import Path

app = FastAPI()

TOOL_URL = os.environ.get("TOOL_URL", "http://tool-service:8001/run")
PROMPT_PATH = os.environ.get("PROMPT_PATH", "/prompts/default.txt")
TRACES_DIR = os.environ.get("TRACES_DIR", "/traces")
OBS_URL = os.environ.get("OBS_URL", "http://observability:9000/trace")
AGENT_VERSION = os.environ.get("AGENT_VERSION", "v1")

Path(TRACES_DIR).mkdir(parents=True, exist_ok=True)


def compute_prompt_version(text: str) -> str:
    """Derive the prompt version from its actual content so the version tag
    changes automatically whenever the ConfigMap-mounted prompt file changes,
    instead of relying on a manually-set PROMPT_VERSION env var that can
    silently drift out of sync with the real prompt content."""
    if not text:
        return "unknown"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


class InvokeRequest(BaseModel):
    input: str
    request_id: str | None = None


@app.post("/invoke")
async def invoke(req: InvokeRequest):
    request_id = req.request_id or str(uuid.uuid4())
    prompt_text = ""
    try:
        # read raw bytes and try multiple encodings to be robust on Windows saved files
        raw = Path(PROMPT_PATH).read_bytes()
        for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
            try:
                prompt_text = raw.decode(enc)
                break
            except Exception:
                continue
    except Exception:
        prompt_text = ""

    tool_payload = {
        "request_id": request_id,
        "action": "default",
        "args": {"input": req.input, "prompt": prompt_text},
    }

    start = time.time()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(TOOL_URL, json=tool_payload)
            r.raise_for_status()
            tool_resp = r.json()
            status = "ok"
        except Exception as e:
            tool_resp = {"error": str(e)}
            status = "error"
    duration_ms = int((time.time() - start) * 1000)

    trace = {
        "request_id": request_id,
        "timestamp": time.time(),
        "prompt_version": compute_prompt_version(prompt_text),
        "prompt_text": prompt_text,
        "agent_version": AGENT_VERSION,
        "tool_version": tool_resp.get("tool_version" if isinstance(tool_resp, dict) else "", ""),
        "tool_latency_ms": tool_resp.get("duration_ms") if isinstance(tool_resp, dict) else None,
        "agent_total_ms": duration_ms,
        "status": status,
        "input": req.input,
    }

    # send trace to observability collector; fallback to local write if POST fails
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.post(OBS_URL, json=trace)
            r.raise_for_status()
            obs_resp = r.json()
            trace_result = {"sent": True, "observability": obs_resp}
        except Exception as e:
            # fallback: write trace locally
            try:
                trace_path = Path(TRACES_DIR) / f"{request_id}.json"
                trace_path.write_text(json.dumps(trace))
            except Exception:
                pass
            trace_result = {"sent": False, "error": str(e)}

    return {"request_id": request_id, "tool_result": tool_resp, "status": status, "prompt_version": trace["prompt_version"], "trace": trace_result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
