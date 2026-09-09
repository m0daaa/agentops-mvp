from fastapi import FastAPI
from pydantic import BaseModel
import time
import os
import random
import httpx
from pathlib import Path

app = FastAPI()
TOOL_VERSION = os.environ.get("TOOL_VERSION", "v1")

# 是否呼叫 model-service。預設關閉：K8s 部署（k8s/tool-deployment.yaml）維持
# 這個旗標關閉，確保 Experiment B 已經量測過的 CPU/HPA 行為不會因為多一段
# 網路呼叫而改變；docker-compose 本機環境則預設開啟，用來展示三段式呼叫鏈
# （agent -> tool -> model）跟 model_version 有沒有正確傳到 trace 裡。
CALL_MODEL = os.environ.get("CALL_MODEL", "false").lower() == "true"
MODEL_URL = os.environ.get("MODEL_URL", "http://model-service:8080/predict")


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

    # 呼叫 model-service（若有開啟）。刻意獨立於上面的 duration_ms 計算之外，
    # 不計入 tool 自己的耗時，避免影響 Experiment B 已經定案的延遲數據。
    model_version = None
    prediction = None
    if CALL_MODEL:
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.post(
                    MODEL_URL,
                    json={"request_id": req.request_id, "input": req.args.get("input", "")},
                )
                r.raise_for_status()
                model_resp = r.json()
                model_version = model_resp.get("model_version")
                prediction = model_resp.get("prediction")
                model_status = "ok"
        except Exception as e:
            model_status = f"error:{e}"
    else:
        model_status = "disabled"

    result = {
        "request_id": req.request_id,
        "tool_version": TOOL_VERSION,
        "duration_ms": duration_ms,
        "result": {"echo": req.args.get("input", "").upper()},
        "received_prompt": received_prompt,
        "prompt_len": len(received_prompt),
        "status": "ok",
        "model_version": model_version,
        "prediction": prediction,
        "model_status": model_status,
    }
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
