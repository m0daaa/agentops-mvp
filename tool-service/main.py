from fastapi import FastAPI
from pydantic import BaseModel
import time
import os
import random
from pathlib import Path

app = FastAPI()
TOOL_VERSION = os.environ.get("TOOL_VERSION", "v1")


class RunRequest(BaseModel):
    request_id: str
    action: str
    args: dict


@app.post("/run")
def run(req: RunRequest):
    start = time.time()
    # simulate work
    sleep_ms = int(os.environ.get("TOOL_SLEEP_MS", "100"))
    busy_ms = int(os.environ.get("TOOL_BUSY_MS", "0"))
    if busy_ms > 0:
        # busy-wait for busy_ms milliseconds to generate CPU load (for HPA testing)
        end = time.time() + (busy_ms / 1000.0)
        x = 0
        while time.time() < end:
            x += 1
        duration_ms = int((time.time() - start) * 1000)
    else:
        time.sleep(sleep_ms / 1000.0)
        duration_ms = int((time.time() - start) * 1000)
    duration_ms = int((time.time() - start) * 1000)

    received_prompt = req.args.get("prompt", "")
    result = {
        "request_id": req.request_id,
        "tool_version": TOOL_VERSION,
        "duration_ms": duration_ms,
        "result": {"echo": req.args.get("input", "").upper()},
        "received_prompt": received_prompt,
        "prompt_len": len(received_prompt),
        "status": "ok",
    }
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
