# artifacts/bench 說明

這份文件幫你看懂 `artifacts/bench/` 底下每個檔案是什麼、對應哪個實驗，5 分鐘內知道該看哪份。

## 正式證據（EXPERIMENT_SUMMARY.md / 各報告有引用）

| 檔案 | 對應 | 說明 |
|---|---|---|
| `bench_results.md` | Agent vs Baseline | 解耦版 agent-service 與單體版 baseline 的延遲/吞吐對比報告 |
| `hpa_tool_scaling.md` | Experiment B | HPA 觸發、tool 層獨立擴展的核心結論報告 |
| `bench_agent.csv` | Agent vs Baseline | `bench_results.md` 引用的 agent 原始壓測數據 |
| `bench_baseline.csv` | Agent vs Baseline | `bench_results.md` 引用的 baseline（單體）原始壓測數據 |
| `bench_tool_cpu_heavy.csv` | Experiment B | README.md 引用，CPU-heavy 工作負載下的原始壓測數據 |
| `bench_tool_before_hpa.csv` | Experiment B | `hpa_tool_scaling.md`「Benchmark evidence」區塊裡第一筆乾淨數據的來源檔 |
| `bench_tool_after_hpa.csv` | Experiment B | `hpa_tool_scaling.md`「Benchmark evidence」區塊裡第二筆乾淨數據的來源檔 |
| `prompt_update_latency.csv` | Experiment A | `EXPERIMENT_SUMMARY.md` 引用，ConfigMap 更新延遲的原始量測數據 |
| `docs/bench_latency.png`、`docs/bench_throughput.png` | Agent vs Baseline | `bench_results.md` 內嵌的圖表 |
| `scripts/plot_bench.py` | — | 把上面幾個 CSV 畫成圖表的腳本 |

## archive/（歷史嘗試，目前沒有任何報告引用）

這幾個檔案是之前反覆調參、嘗試不同做法留下的原始輸出，**目前的結論不依賴這些檔案**，保留只是為了不遺失實驗過程紀錄：

- `bench_agent_scale_test.csv`、`bench_k8s_tool.csv`、`bench_tool.csv`：早期探索性的小規模壓測，後來被上面「正式證據」欄位裡同名不同檔的正式版本取代。
- `tool_after_hpa_clean.csv`、`tool_before_hpa_clean.csv`：**注意檔名雖然叫 "clean"，內容其實是失敗率很高的一次嘗試**（部分測試 3000 筆請求裡 3000 筆都逾時/出錯），推測是想做更嚴謹的 before/after 對比但撞到已知的 `kubectl port-forward` 限制（見 `EXPERIMENT_SUMMARY.md`）。目前正式引用的「乾淨數據」其實是 `bench_tool_before_hpa.csv` / `bench_tool_after_hpa.csv` 裡那兩筆 errors=0 的記錄，不是這兩個檔案。

如果之後要接續做 `Next_Phase_Action_Plan.md` 裡提到的「叢集內流量產生器」，這裡的失敗紀錄可以當作「為什麼需要換一種打流量方式」的佐證。
