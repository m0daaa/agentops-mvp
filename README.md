# AgentOps MVP

This project is a compact AgentOps prototype for validating a decoupled architecture: agent logic, tool execution, and observability are separated into services instead of being bundled into a single process.

The main goal is to test whether a slow or busy tool layer can be handled by scaling only the tool service, while keeping the agent layer stable.

## Project structure

- [agent-service](agent-service): FastAPI service that receives agent requests and calls the tool service.
- [tool-service](tool-service): CPU-heavy /run endpoint used for tool-side load and autoscaling tests.
- [baseline](baseline): monolithic control service for comparison.
- [observability](observability): trace collector that stores request traces.
- [prompts](prompts): prompt payloads and config used by the agent.
- [k8s](k8s): Kubernetes deployment manifests and Minikube setup instructions.
- [artifacts/bench](artifacts/bench): benchmark CSVs, plots, and notes for performance and HPA experiments.
- [bench.py](bench.py): concurrent load generator used for local and Kubernetes benchmarking.
- [docker-compose.yml](docker-compose.yml): local multi-service startup for development and smoke testing.

## Core experiment

The key validation question is:

> Can the decoupled system scale only the tool layer when the tool becomes the bottleneck?

This is tested by sending direct CPU-heavy traffic to the tool service and observing whether the Kubernetes HPA scales the tool deployment without requiring the agent service to scale as well.

The experiment evidence is summarized in:

- [artifacts/bench/hpa_tool_scaling.md](artifacts/bench/hpa_tool_scaling.md)
- [k8s/hpa.yaml](k8s/hpa.yaml)
- [k8s/README.md](k8s/README.md)

## Quick start

### Local with Docker Compose

```bash
docker compose up --build
```

Then call the agent:

```bash
curl -X POST http://localhost:8000/invoke -H "Content-Type: application/json" -d '{"input":"hello"}'
```

Traces are written to the traces volume managed by the observability collector.

### Benchmarking

```powershell
pip install requests
python bench.py --url http://localhost:8000/invoke --concurrency 10 --requests 100
```

For tool-specific load tests:

```powershell
python bench.py --url http://localhost:8001/run --format tool --concurrency 500 --requests 10000
```

## Benchmark artifacts

The benchmark outputs are kept under [artifacts/bench](artifacts/bench):

- [artifacts/bench/bench_agent.csv](artifacts/bench/bench_agent.csv)
- [artifacts/bench/bench_baseline.csv](artifacts/bench/bench_baseline.csv)
- [artifacts/bench/bench_tool_cpu_heavy.csv](artifacts/bench/bench_tool_cpu_heavy.csv)
- [artifacts/bench/bench_results.md](artifacts/bench/bench_results.md)
- [artifacts/bench/hpa_tool_scaling.md](artifacts/bench/hpa_tool_scaling.md)

The consolidated analysis in [artifacts/bench/bench_results.md](artifacts/bench/bench_results.md) compares the decoupled agent path against the monolithic baseline.

## Kubernetes / HPA validation

For the Minikube autoscaling experiment, use the manifests in [k8s](k8s):

- [k8s/tool-deployment.yaml](k8s/tool-deployment.yaml)
- [k8s/hpa.yaml](k8s/hpa.yaml)
- [k8s/minikube_setup.ps1](k8s/minikube_setup.ps1)

The observed HPA evidence is that the tool-service deployment scaled from 1 replica to 4 and then 5 replicas under CPU-heavy tool load, with the HPA target rising from about 5%/50% to 1605%/50% before stabilizing.

This is the core proof that the decoupled architecture can isolate tool-side scaling and respond directly to tool bottlenecks.

## Documentation policy

Keep project artifacts organized by responsibility:

- source code and service logic stay in the service folders
- cluster configuration remains in [k8s](k8s)
- raw measurements and plots stay in [artifacts/bench](artifacts/bench)
- the top-level README stays as a summary and navigation page, not a dump of all experimental detail

This keeps the project easy to maintain as the experiment grows.

