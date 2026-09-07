enKubernetes HPA / Tool-scaling test
================================

This folder contains example manifests to deploy `tool-service` in Kubernetes and an `HorizontalPodAutoscaler` that targets CPU utilization.

Important note: the default `tool-service` work simulation uses `time.sleep` which does not consume CPU. To trigger CPU-based HPA we provide `TOOL_BUSY_MS` which performs a short CPU busy-wait inside the handler when set (>0).

Prerequisites
- A Kubernetes cluster (Minikube, Kind, or cloud). For Minikube, enable metrics-server: `minikube addons enable metrics-server` or install metrics-server in cluster.
- `kubectl` configured to talk to the cluster.

Quick test steps (Minikube)

1. Build and load the `tool-service` image into the cluster (Minikube example):

```bash
docker build -t tool-service:latest ../tool-service
minikube image load tool-service:latest
```

2. Apply the deployment and service:

```bash
kubectl apply -f ../k8s/tool-deployment.yaml
```

3. Apply the HPA:

```bash
kubectl apply -f ../k8s/hpa.yaml
```

4. Patch the deployment to enable CPU busy work (e.g., 300ms per request):

```bash
kubectl set env deployment/tool-service TOOL_BUSY_MS=300
```

5. Generate load (from a pod or external host) against the service ClusterIP or using port-forward:

```bash
# port-forward locally
kubectl port-forward svc/tool-service 8001:8001 &
# run the bench script from your machine or from another pod
python bench.py --url http://localhost:8001/run --format tool --concurrency-list 10,25,50 --requests 200 --repeat 3 --csv bench_k8s_tool.csv
```

6. Watch HPA and pods scale:

```bash
kubectl get hpa -w
kubectl get pods -l app=tool-service -w
```

7. Compare metrics before/after scaling using the CSV results.

Notes
- If your cluster lacks `metrics-server`, HPA will not be able to scale on CPU. For local testing prefer Minikube with metrics-server enabled or Kind with metrics-server installed.
- Adjust `TOOL_BUSY_MS` to control CPU pressure. `TOOL_SLEEP_MS` still models I/O/latency but won't raise CPU.

Troubleshooting: HPA stays at low CPU
------------------------------------

If `kubectl get hpa` shows metrics such as `cpu: 1%/50%` but replicas never increase, HPA is working but the target pod is not consuming enough CPU. Check these in order.

1. Confirm the Kubernetes deployment has CPU busy work enabled:

```powershell
kubectl exec deploy/tool-service -- printenv TOOL_BUSY_MS
```

If it prints `0` or nothing, set it higher and restart the pod:

```powershell
kubectl set env deployment/tool-service TOOL_BUSY_MS=1000
kubectl rollout restart deployment/tool-service
kubectl rollout status deployment/tool-service
kubectl exec deploy/tool-service -- printenv TOOL_BUSY_MS
```

2. Confirm local port `8001` is really forwarded to Kubernetes, not occupied by Docker Compose:

```powershell
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

If a Docker Compose container already publishes `0.0.0.0:8001->8001/tcp`, stop the compose stack or forward Kubernetes to another local port:

```powershell
docker compose down
kubectl port-forward svc/tool-service 18001:8001
```

Then benchmark against `http://localhost:18001/run`.

3. Confirm the benchmark uses the tool payload format:

```powershell
..\.venv\Scripts\python.exe bench.py --url http://localhost:18001/run --format tool --concurrency-list 25,50,100 --requests 1000 --repeat 1 --csv artifacts/bench/bench_k8s_tool.csv
```

4. Watch both HPA and pod CPU while the benchmark is still running:

```powershell
kubectl get hpa -w
kubectl top pods
```
