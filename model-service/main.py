from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# 刻意「不」做成可以用 `kubectl set env` 隨手覆蓋的 runtime 環境變數。
# MODEL_VERSION 綁定在 image 裡：要換版本就要重新 build + deploy 一個新 image，
# 跟真實世界「換模型 = 換一份權重檔」是同一種節奏，而不是改一個 config flag。
# 呼應 compute_prompt_version() 的設計哲學（見 agent-service/main.py），
# 也對應 AgentOps_Next_Phase_Action_Plan.md 的「缺漏 5」。
MODEL_VERSION = "v1"


class PredictRequest(BaseModel):
    request_id: str
    input: str = ""


@app.post("/predict")
def predict(req: PredictRequest):
    # 這不是真的模型推論，只是一個 mock：長度決定輸出內容，
    # 重點是驗證「model_version 能不能隨 image 版本正確傳遞到 trace 裡」，
    # 不是驗證推論品質（本專題不做模型訓練/推論優化）。
    prediction = f"mock-prediction({len(req.input)} chars)"
    return {
        "request_id": req.request_id,
        "model_version": MODEL_VERSION,
        "prediction": prediction,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
