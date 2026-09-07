# EXPERIMENT_SUMMARY — AgentOps MVP 實驗結論總結

> 本文件是三個實驗（Prompt 更新、Tool 獨立擴展、Trace 完整性）的最終彙整結論，取代散落在
> `artifacts/bench/*.md` 裡的個別筆記。撰寫原則：只寫已經被數據支持的結論，並誠實標出還沒
> 驗證到的邊界，不誇大。

## 一句話結論

**解耦架構能把工具層（Tool）的效能瓶頸隔離出來，並透過 Kubernetes HPA 做到「只放大瓶頸元件、
不放大整個 Agent 堆疊」的精準擴展；同時 Prompt 可以透過 ConfigMap 動態更新、不需重建 Agent
image（實測生效時間約數十秒級，見 Experiment A）。這兩點是本專題目前最站得住腳的實證結果。**

至於「解耦後系統整體 throughput/latency 是否優於單體架構」，目前證據還不足以支持這個更強的主張
（見 Experiment B 的邊界說明）。

---

## Experiment A — Prompt Update Latency

**狀態：✅ 驗證完成，已量化**

- 作法：把 prompt 從寫死在程式碼裡，改成放在 K8s ConfigMap，agent-service 每次 request 動態讀取。
- Prompt 版本標記從原本寫死的 `PROMPT_VERSION` 環境變數，改成對讀到的 prompt 內容做 SHA-256
  取前 8 碼（`compute_prompt_version()`），讓版本號會自動反映 ConfigMap 內容的變化，不需要人工
  同步更新環境變數。
- 量測方法：`measure_prompt_update_latency.py` 自動用一組帶隨機 marker 的新內容更新 ConfigMap
  （保證每次都能明確偵測到「內容真的變了」），從 `kubectl apply` 送出的當下開始計時，輪詢
  `/invoke` 回傳的 `prompt_version`，直到出現與新內容相符的 hash 為止。

- **量測結果（Minikube 環境，5 次重複，全部成功偵測到更新）：**

  | 統計量 | 數值 |
  |---|---:|
  | 樣本數 | 5 |
  | 平均 (mean) | 57.2 秒 |
  | 最快 (min) | 13.3 秒 |
  | 最慢 (max) | 81.4 秒 |

  原始數據：`artifacts/bench/prompt_update_latency.csv`

- **結論：** ConfigMap 更新到生效的時間**不是穩定的秒級**，而是落在十幾秒到一分半之間、右偏
  （大部分集中在 60 秒上下）的分布。這個變異來自 Kubernetes kubelet 對 ConfigMap Volume 的
  週期性同步機制，不是本專題實作上的缺陷。即便如此，相較於單體式架構「改 prompt 需要重新
  build image、push image、restart deployment」動輒數分鐘甚至更久的流程，ConfigMap 版本仍然
  快上一個數量級以上，而且整個過程中 agent-service 完全不需要重啟、沒有觀察到 request 失敗。

**正確的講法：** 「Prompt 更新不需要重新部署 Agent，生效時間落在數十秒等級（受 Kubernetes
ConfigMap 同步機制影響），而不是嚴格意義上的『即時』或『秒級』。」這比最初「秒級生效」的說法更
精確，被追問細節時也站得住腳。

---

## Experiment B — Tool Scaling Isolation

**狀態：✅ 核心機制已驗證；量化 throughput 對比受限於本機測試工具，非架構問題**

### 已經證明的事（K8s 控制平面證據，可信度最高）

- Tool-service 是獨立的 K8s Deployment + Service，`tool-service-hpa` 以 CPU utilization 為指標
  （target `averageUtilization: 50`）。
- 多次獨立測試中都觀測到 HPA 依 CPU 訊號自動擴展 tool-service：從最初的 1→2（CPU 69%），到後來
  在持續負載下擴到上限 1→5。
- 每一次擴展過程中，agent-service 的 replica 數量從未變動——瓶頸只出現在 tool 層，也只有 tool
  層被放大，agent 層完全不受影響。

**這是本專題最核心的架構主張，而且直接來自 Kubernetes 控制平面本身的狀態
（`kubectl get hpa`、`kubectl get deployment`），不依賴任何 benchmark 工具，可信度最高：
「Tool 是共用且可能成為瓶頸的元件，解耦後可以只針對它擴展，而不必連 Agent runtime 一起複製。」**

### 為什麼沒有做出「擴展後 throughput 提升多少」的量化對比

在同一組固定變因（`TOOL_BUSY_MS=500`, `concurrency=20`, `requests=3000`, `repeat=3`）下，跑了
乾淨、零錯誤的 before(1 replica) / after(5 replica) 對照：

| 情境 | throughput (mean) | p95 latency (mean) |
|---|---:|---:|
| BEFORE：1 replica | 11.9 req/s | 2336.0 ms |
| AFTER：5 replica | 12.2 req/s | 2284.5 ms |

兩組數字幾乎沒有差異。深入排查後確認原因**不是 workload 沒調好，而是 `kubectl port-forward` 這個
本機測試路徑本身的限制**：`kubectl port-forward` 對一個 Service 執行時，只會在啟動當下隨機選定
「一顆」後端 pod，把整個 session 釘死轉發到那一顆 pod，並不會像叢集內部透過 kube-proxy 呼叫
Service 那樣在多個 replica 間做負載平衡。這點有明確證據支持：多次測試中斷線 log 顯示轉發目標
的 pod UID（`f3568f3e...`）完全相同，即使當下 HPA 已經把 replica 數擴到 5 個。也就是說，這個
benchmark 從頭到尾都只打到同一顆 pod，HPA 多開出來的那幾個 replica 完全沒有分到流量——這是
測試路徑的限制，不是架構本身的缺陷。

**這不影響核心論點成立，理由如下：**

1. 「Tool 可以獨立擴展、Agent 不用跟著擴展」這件事，證據來自 Kubernetes 自己的控制平面狀態
   （HPA 決策、replica 數量），跟流量實際被路由到哪一顆 pod 無關，是獨立、可信的證據來源。
2. 「多個 replica 之間會被 Service 正確負載平衡」這件事，是 Kubernetes 本身（kube-proxy）行之
   有年、被廣泛驗證過的標準行為，不是本專題架構設計要提出或重新驗證的主張。
3. `kubectl port-forward` 不支援 Service 層級負載平衡是官方文件與社群都認可的已知限制（它被
   設計為除錯用途，不是 load-testing 用途）。本專題受限於本機 Minikube + Windows 環境，沒有
   進一步搭建叢集內部的流量產生器來繞開這個限制，這是明確揭露的測試工具邊界，不是結果本身
   有問題。

**結論：** 解耦架構支援「針對瓶頸元件做精準擴展」這個核心價值已經被驗證，且證據來自最可靠的
K8s 控制平面狀態；而「擴展後 end-to-end throughput 實際提升多少」這個更進一步的量化問題，受限
於本機測試環境的工具限制，本專題誠實地將其列為未完成項目，而非給出一個可能誤導的數字。

---

## Experiment C — Trace Completeness

**狀態：✅ 基本可審計，已驗證**

### 已經做到的事

- `agent-service` 每次 `/invoke` 都會產生一筆 trace，欄位包含：`request_id`、`prompt_version`、
  `agent_version`、`tool_version`、`tool_latency_ms`、`agent_total_ms`、`status`。
- `observability/collector.py` 補上 `GET /trace/{request_id}`（查單筆完整紀錄）與 `GET /traces`
  （列出最近的 trace），並補了對應的 K8s manifest（`k8s/observability-deployment.yaml`），解決了
  agent-service 在 Minikube 裡原本連不到 observability 的問題（之前因為缺 Service 一直是 DNS
  找不到主機名，只能 fallback 寫 agent 自己 pod 的本機檔案）。
- 已用 CLI 工具 `query_trace.py` 實測驗證整條路徑：呼叫一次 `/invoke` 後，`trace.sent` 從原本的
  `false` 變成 `true`；`query_trace.py --list` 能看到這筆 request；`query_trace.py
  --request-id <id>` 能查到完整紀錄，包含 `prompt_version`、`tool_latency_ms`、
  `agent_total_ms`、`status` 等欄位。**這就是驗收標準要求的「給一個 request_id，可以知道它用了
  哪一版 prompt、花了多少時間、成功或失敗」。**

### 還缺的部分（誠實邊界）

- 目前是 agent-service 統一彙整一筆 trace（把 tool-service 回傳的 `tool_version`、
  `tool_latency_ms` 併進同一筆紀錄），而不是 agent 和 tool 各自上報、查詢時再關聯——嚴格來說跟
  論文講的 waterfall trace（每個服務各自留下一段 span，再依 request_id 串起來）不是同一種做法，
  但對兩層架構而言，效果上已經能回答「這個 request 在哪一步花了多少時間」。
- 沒有 token / cost 模擬值欄位。
- Trace 資料存在 observability pod 自己的檔案系統裡（沒有掛 PersistentVolume），pod 重建就會
  遺失歷史記錄，不適合當正式的稽核儲存，但作為 MVP demo 已經足夠。

**結論：** 可觀測性骨架不只存在，而且已經驗證「給 request_id 查完整執行路徑」這件事真的可行，
Experiment C 的驗收標準基本達成。

---

## 整體定位

到目前為止，這個專題已經證明：

1. **Component Decoupling 是可行的**——Agent、Tool、Prompt 三者可以獨立部署、獨立版本管理。
2. **Independent Targeted Scaling 是可行的**——HPA 可以只針對瓶頸元件（Tool）擴展，Agent 層不受影響，
   證據來自 K8s 控制平面本身的狀態，不依賴本機 benchmark 工具。
3. **可觀測性已可查詢、可審計**——每次執行都有結構化 trace，且能用 request_id 查到完整執行紀錄
   （Experiment C 已驗證）。
4. **Prompt 更新延遲已量化**——平均約 57 秒、範圍 13–81 秒，明顯快於單體式的分鐘級重新部署。

同時也誠實地知道邊界在哪裡：

- 擴展後 end-to-end throughput 的量化對比未能完成，原因是本機測試環境依賴 `kubectl
  port-forward`，而它不支援 Service 層級負載平衡（詳見 Experiment B 的技術說明），並非架構或
  workload 設計問題；因此本專題不主張「解耦後整體效能更好」，只主張「解耦後可以精準擴展瓶頸」
  ——這個較窄但誠實的主張已由 K8s 控制平面證據獨立驗證。
- 目前的 workload 是合成（synthetic）的，且需要手動調校才能穩定觸發 HPA。
- 沒有接上真實 LLM model（in-scope 決策，非缺陷）。
- Trace 儲存沒有持久化（無 PVC），且是 agent 端統一彙整而非各服務各自上報的標準分散式 tracing
  模式。

---

## 下一步該怎麼走

按照投入報酬排序：

1. **`DEMO_GUIDE.md` / 最終總結（1-2 天）**
   說明如何用 Minikube 重現整個流程、如何觀察 HPA scaling、如何用 `query_trace.py` 查一次執行
   紀錄。

2. **檔案導航整理（`artifacts/README.md` 等，半天）**
   優先度最低，但能讓任何人 5 分鐘內看懂專題做了什麼、證明了什麼、還缺什麼。

3. **（可選、未來工作）在叢集內部架設流量產生器，繞開 `kubectl port-forward` 的限制**
   如果之後還想把 Experiment B 的量化 throughput 對比補完整，需要在叢集裡開一個一次性的
   load-generator pod，直接透過 Service 名稱（`http://tool-service:8001/run`）打流量，讓
   kube-proxy 的負載平衡機制真正介入。這需要額外處理 `kubectl exec`/`kubectl cp` 的自動化，
   投入產出比對這學期的範圍來說不高，列為下學期或有餘力時再做的項目，不是現階段的優先事項。
