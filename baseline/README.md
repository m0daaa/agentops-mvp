Monolithic baseline for AgentOps MVP
===================================

This service bundles agent and tool logic into a single container to serve as a "monolithic baseline" for experiments.

Run locally (from this folder):

```powershell
docker build -t agentops-baseline:latest .
docker run --rm -p 8002:8000 -v ${PWD}/../prompts:/prompts -v ${PWD}/../traces:/traces agentops-baseline:latest
```

The service listens on port `8000` inside the container (mapped to `8002` above). It exposes `POST /invoke` and writes traces into `/traces`.
