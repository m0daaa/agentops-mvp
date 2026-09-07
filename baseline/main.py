from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
import time
import os
import json
import uuid


class InvokeRequest(BaseModel):
    input: str | None = None


app = FastAPI(title="AgentOps Monolithic Baseline")

TOOL_SLEEP_MS = int(os.getenv("TOOL_SLEEP_MS", "100"))
BASELINE_VERSION = os.getenv("BASELINE_VERSION", "baseline-0.1")
TRACES_DIR = os.getenv("TRACES_DIR", "/traces")
PROMPT_PATH = os.getenv("PROMPT_PATH", "/prompts/default.txt")


async def run_tool_sim(prompt: str) -> str:
    # Simulate tool processing work
    await asyncio.sleep(TOOL_SLEEP_MS / 1000.0)
    return prompt.upper()


def read_prompt_bytes(path: str) -> str:
    # robust decoding with fallback encodings
    encs = ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "latin-1"]
    try:
        data = open(path, "rb").read()
    except Exception:
        return ""
    for e in encs:
        try:
            return data.decode(e)
        except Exception:
            continue
    return data.decode("latin-1", errors="ignore")


@app.post("/invoke")
async def invoke(req: InvokeRequest):
    request_id = str(uuid.uuid4())
    start = time.time()

    prompt_text = read_prompt_bytes(PROMPT_PATH)

    try:
        result = await run_tool_sim(prompt_text)
        status = "ok"
    except Exception as e:
        result = ""
        status = "error"

    duration_ms = int((time.time() - start) * 1000)

    trace = {
        "request_id": request_id,
        "baseline_version": BASELINE_VERSION,
        "duration_ms": duration_ms,
        "status": status,
        "result": result,
        "prompt_len": len(prompt_text),
        "prompt_text": prompt_text[:1000],
    }

    try:
        os.makedirs(TRACES_DIR, exist_ok=True)
        with open(os.path.join(TRACES_DIR, f"{request_id}.json"), "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)
    except Exception:
        # don't fail the request if trace writing fails
        pass

    return {"request_id": request_id, "duration_ms": duration_ms, "status": status, "result": result}
