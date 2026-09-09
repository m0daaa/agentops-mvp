from fastapi import FastAPI, HTTPException, Request
from pathlib import Path
import json
import os

app = FastAPI()
TRACES_DIR = os.environ.get("TRACES_DIR", "/traces")
Path(TRACES_DIR).mkdir(parents=True, exist_ok=True)


@app.post("/trace")
async def receive_trace(req: Request):
    body = await req.json()
    request_id = body.get("request_id") or body.get("requestId") or "unknown"
    path = Path(TRACES_DIR) / f"{request_id}.json"
    path.write_text(json.dumps(body))
    return {"status": "received", "request_id": request_id}


@app.get("/trace/{request_id}")
async def get_trace(request_id: str):
    """Look up one trace by request_id -- the minimal 'audit' query the
    Action Plan asked for: given a request_id, see the full execution
    record (prompt version, tool latency, status, ...)."""
    path = Path(TRACES_DIR) / f"{request_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no trace found for request_id={request_id}")
    return json.loads(path.read_text())


@app.get("/traces")
async def list_traces(limit: int = 50):
    """List the most recent traces (newest first) so you can browse what
    request_ids exist without already knowing one."""
    files = sorted(Path(TRACES_DIR).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        try:
            body = json.loads(p.read_text())
        except Exception:
            body = {}
        out.append({
            "request_id": p.stem,
            "timestamp": body.get("timestamp"),
            "status": body.get("status"),
            "prompt_version": body.get("prompt_version"),
            "model_version": body.get("model_version"),
        })
    return {"count": len(out), "traces": out}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
