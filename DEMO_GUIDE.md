# DEMO_GUIDE

這份文件是給「第一次看到這個專案的人」（教授、口試委員、或未來的你）用的操作手冊，目標是：**5-10 分鐘內，從零把整個系統跑起來，並且看到三個實驗的證據**。結論與數據以 `EXPERIMENT_SUMMARY.md` 為準，這份文件只講「怎麼動手重現」。

## 0. 前置需求

- Docker Desktop（或任何能跑 `docker` / `docker compose` 的環境）
- Minikube（`minikube version` 確認已安裝）
- kubectl（`kubectl version --client` 確認已安裝）
- Python 3.11+，並 `pip install requests`

---

## 1. 最快路徑：本機 Docker Compose（驗證系統邏輯，不含 K8s / HPA）

不需要 K8s，用來快速確認 agent-service / tool-service / observability 三個服務彼此串接沒問題。

```bash
cd agentops-mvp
docker compose up --build
```

另開一個終端機，打一次完整呼叫鏈：

```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"input":"hello","request_id":"demo-1"}'
```

回傳的 JSON 裡應該看到 `"status":"ok"`、`prompt_version`（一組由 prompt 內容算出來的 hash）、以及 `trace` 欄位。這代表 agent → tool → observability 這條路徑是通的。

跑完按 `Ctrl+C`，或另開終端機 `docker compose down`。

---

## 2. 完整路徑：Minikube 上的 K8s 部署

這是用來展示 Experiment A（Prompt 更新）、Experiment B（HPA 獨立擴展）、Experiment C（Trace 查詢）的正式環境。

### 2.1 啟動叢集並啟用 metrics-server

```bash
minikube start
minikube addons enable metrics-server
```

`metrics-server` 是 HPA 讀取 CPU 使用率的來源，沒開這個 Experiment B 的 HPA 永遠不會觸發。

### 2.2 把三個服務的 image 建好、載進 Minikube

```bash
cd agentops-mvp
docker build -t agent-service:latest ./agent-service
docker build -t tool-service:latest ./tool-service
docker build -t observability:latest ./observability

minikube image load agent-service:latest
minikube image load tool-service:latest
minikube image load observability:latest
```

（`k8s/minikube_setup.ps1` 是針對 tool-service 單獨的懶人腳本，如果你只想重現 Experiment B 可以直接跑那支；上面手動三行是為了同時把 agent/observability 也部署起來，走完整套 demo。）

### 2.3 套用 K8s manifests

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/agent-deployment.yaml
kubectl apply -f k8s/tool-deployment.yaml
kubectl apply -f k8s/observability-deployment.yaml
kubectl apply -f k8s/hpa.yaml
```

確認都起來了：

```bash
kubectl get pods
kubectl get hpa
```

應該看到 `agent-service`、`tool-service`、`observability` 三個 Deployment 各一個 Running pod，以及 `tool-service-hpa` 這個 HPA（`MINPODS 1`、`MAXPODS 5`）。

### 2.4 打通對外連線（port-forward）

開三個終端機分別跑：

```bash
kubectl port-forward svc/agent-service 8000:8000
kubectl port-forward svc/tool-service 8001:8001
kubectl port-forward svc/observability 9000:9000
```

保持這三個視窗開著，後面的步驟都要用到。

---

## 3. Experiment A 重現：Prompt 更新免重啟

先打一次請求，記下目前的 `prompt_version`：

```bash
curl -X POST http://localhost:8000/invoke -H "Content-Type: application/json" -d '{"input":"before-update"}'
```

修改 `k8s/configmap.yaml` 裡 `default.txt` 的內容（隨便加一句話），重新 apply：

```bash
kubectl apply -f k8s/configmap.yaml
```

**不要重啟 agent-service 的 pod**，等個幾十秒（ConfigMap 掛載的更新透過 kubelet 週期性同步，實測平均約 57 秒、範圍 13-81 秒，詳見 `EXPERIMENT_SUMMARY.md`），再打一次同樣的請求：

```bash
curl -X POST http://localhost:8000/invoke -H "Content-Type: application/json" -d '{"input":"after-update"}'
```

比較兩次回傳的 `prompt_version`：不一樣，就代表 prompt 內容真的换了，而且全程沒有重建 image、沒有重啟 pod。如果想精確量測這個延遲，用 `measure_prompt_update_latency.py`。

---

## 4. Experiment B 重現：Tool 層獨立擴展（HPA）

打開 CPU 忙碌模式，讓 tool-service 有東西可以擴展：

```bash
kubectl set env deployment/tool-service TOOL_BUSY_MS=500
```

另開一個終端機，持續觀察 HPA 跟 pod 數量：

```bash
kubectl get hpa -w
```

（保持這個視窗開著，等一下會即時看到 REPLICAS 從 1 變 2 甚至更多）

再開一個終端機，對 tool-service 打壓測流量：

```bash
python bench.py --url http://localhost:8001/run --format tool --concurrency 100 --requests 10000
```

觀察 `kubectl get hpa -w` 那個視窗：CPU 使用率應該會超過 HPA 設定的 `50%` 門檻，REPLICAS 開始從 1 往上加。同時可以另外確認 agent-service 全程沒有被影響：

```bash
kubectl get pods -l app=agent-service
```

應該只有 1 個 pod，不會跟著 scale——這就是「精準擴展瓶頸，而不是整包複製」的核心證據。

**注意（誠實邊界）**：這裡用 `kubectl port-forward` 打流量，測到的是「HPA 有沒有觸發」，不是嚴謹的 throughput 對比（port-forward 不支援 Service 層級負載平衡，會釘死轉發到單一 pod）。量化的 before/after 數據已經記錄在 `artifacts/bench/hpa_tool_scaling.md`，這裡的 demo 是讓人親眼看到 HPA 這個 K8s 控制平面行為本身。

---

## 5. Experiment C 重現：用 request_id 查完整執行紀錄

隨便打一次帶著自訂 `request_id` 的請求：

```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"input":"trace-demo","request_id":"demo-trace-001"}'
```

列出最近的 trace：

```bash
python query_trace.py --list
```

查這一筆的完整內容：

```bash
python query_trace.py --request-id demo-trace-001
```

應該會看到 `prompt_version`、`tool_latency_ms`、`agent_total_ms`、`status` 等欄位——這就是「給一個 request_id，能不能知道它用了哪一版 prompt、花了多少時間、成功或失敗」的驗收標準。

---

## 6. CI：push 之後自動驗證

這個 repo 有一個 GitHub Actions workflow（`.github/workflows/ci.yml`），每次 push 到 `main` 會自動：

1. `docker compose build` 確認每個服務的 image 能建起來
2. 啟動 agent-service + tool-service，打一次真實的 `/invoke` 驗證 `status: ok`
3. 用縮小版 `bench.py` 做一次併發健檢

去 repo 的 **Actions** 分頁可以看到每次 push 的結果（綠勾 = 過、紅叉 = 壞）。這個 CI 只驗證服務本身能不能正常運作，**不會碰 Minikube**，K8s 的部署還是照本文件手動操作。

---

## 7. 收尾

```bash
kubectl delete -f k8s/hpa.yaml -f k8s/observability-deployment.yaml -f k8s/tool-deployment.yaml -f k8s/agent-deployment.yaml -f k8s/configmap.yaml
minikube stop
```

---

## 常見問題

**HPA 一直不擴展，CPU 顯示很低（例如 `1%/50%`）**

1. 確認 `TOOL_BUSY_MS` 真的有設定：`kubectl exec deploy/tool-service -- printenv TOOL_BUSY_MS`，是 `0` 就代表沒生效，重新 `kubectl set env` 一次並 `kubectl rollout restart deployment/tool-service`。
2. 確認打的流量真的走到 Kubernetes 而不是本機還開著的 Docker Compose（兩者都佔用 8001 port 會互相干擾）：`docker ps` 檢查有沒有 compose 容器還在跑，有的話先 `docker compose down`。
3. 確認 `bench.py` 用的是 `--format tool`，不是預設的 `agent` 格式。

更多細節見 `k8s/README.md` 的 Troubleshooting 段落。

**改了 ConfigMap，等很久 prompt 都沒變**

這是已知、誠實記錄的行為，不是 bug——kubelet 同步 ConfigMap Volume 本來就是週期性的，範圍在 13-81 秒之間都算正常，詳見 `EXPERIMENT_SUMMARY.md` Experiment A。
