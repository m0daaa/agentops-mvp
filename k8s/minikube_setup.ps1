<#
Minikube setup script for agentops-mvp

Usage (PowerShell):
  cd <repo>/agentops-mvp/k8s
  ./minikube_setup.ps1

What it does:
- Start minikube if not running
- Enable metrics-server addon
- Build `tool-service` image and load into minikube
- Apply k8s manifests: tool-deployment + hpa
- Set `TOOL_BUSY_MS` env on deployment (default 300ms)

Note: This script only prepares the cluster and applies manifests. Run `kubectl port-forward` and `bench.py` separately.
#>
param(
    [int]$ToolBusyMs = 300,
    [string]$ImageTag = "agentops-mvp-tool-service:latest"
)

Write-Host "Minikube setup script starting..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$k8sPath = Join-Path $repoRoot "k8s"

Write-Host "Repository root: $repoRoot"

# 1) Start minikube if needed
try {
    $status = & minikube status --format '{{.Host}}' 2>$null
    if (-not $status) {
        Write-Host "Minikube not running. Starting minikube..."
        & minikube start
    } else {
        Write-Host "Minikube appears running."
    }
} catch {
    Write-Host "minikube not found or failed to query. Ensure minikube is installed and on PATH." -ForegroundColor Red
    exit 1
}

# 2) Enable metrics-server addon
Write-Host "Enabling metrics-server addon (may be already enabled)..."
& minikube addons enable metrics-server

# 3) Build tool-service image
$toolPath = Join-Path $repoRoot "tool-service"
if (-not (Test-Path $toolPath)) {
    Write-Host "tool-service directory not found at $toolPath" -ForegroundColor Red
    exit 1
}

Write-Host "Building Docker image: $ImageTag"
& docker build -t $ImageTag $toolPath

# 4) Load image into minikube
Write-Host "Loading image into minikube..."
& minikube image load $ImageTag

# 5) Apply manifests (assumes k8s manifests are in this folder)
Write-Host "Applying Kubernetes manifests..."
$toolDeploymentPath = Join-Path $k8sPath "tool-deployment.yaml"
$hpaPath = Join-Path $k8sPath "hpa.yaml"
& kubectl apply -f $toolDeploymentPath
& kubectl apply -f $hpaPath

# 6) Patch deployment to use our image tag (optional: if deployment uses image name)
try {
    Write-Host "Patching deployment image to $ImageTag (if deployment exists)..."
    & kubectl set image deployment/tool-service tool=$ImageTag --record
} catch {
    Write-Host "Failed to patch image; continuing. Check deployment name and image field." -ForegroundColor Yellow
}

# 7) Set TOOL_BUSY_MS env to create CPU pressure for HPA
Write-Host "Setting TOOL_BUSY_MS=$ToolBusyMs on deployment/tool-service"
& kubectl set env deployment/tool-service TOOL_BUSY_MS=$ToolBusyMs

Write-Host "Minikube setup complete."
Write-Host "Next steps:"
Write-Host "  1) Port-forward service locally: kubectl port-forward svc/tool-service 8001:8001" 
Write-Host "  2) Run bench against agent or tool. Examples:"
Write-Host "     python ..\bench.py --url http://localhost:8000/invoke --format agent --concurrency-list 10,25 --requests 200 --repeat 3 --csv ../artifacts/bench/bench_agent.csv"
Write-Host "     python ..\bench.py --url http://localhost:8001/run --format tool --concurrency-list 10,25 --requests 200 --repeat 3 --csv ../artifacts/bench/bench_tool.csv"

Write-Host "Watch HPA and pods: kubectl get hpa -w  and kubectl get pods -l app=tool-service -w"
