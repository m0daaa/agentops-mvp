# Tool-layer HPA Experiment

## Goal

Validate whether a decoupled AgentOps design can isolate tool-side CPU pressure and scale only the tool tier, instead of scaling the entire agent stack together.

This experiment targets the tool services directly:

- Endpoint: `http://localhost:8001/run`
- Format: `tool`
- Metric: tool-service CPU utilization
- HPA target: `averageUtilization: 50`

## Setup

- Deployment: `tool-service`
- HPA: `tool-service-hpa`
- Tool env: `TOOL_BUSY_MS` used to generate synthetic CPU-bound work
- Resource request: `cpu: 200m` after tuning
- Load generator: `bench.py --format tool`
- Workload: direct tool call with fixed concurrency and request count

## Observed HPA behavior

The most reliable HPA signal observed in the tuned configuration was:

```text
NAME               REFERENCE                 TARGETS              MINPODS   MAXPODS   REPLICAS   AGE
tool-service-hpa   Deployment/tool-service   cpu: 69%/50%         1         5         1
tool-service-hpa   Deployment/tool-service   cpu: 69%/50%         1         5         2
```

This indicates that the tool-layer CPU utilization was high enough to trigger autoscaling, and the deployment scaled from 1 replica to 2 replicas under synthetic CPU-heavy load.

## Benchmark evidence

Representative clean runs under the tuned workload (`concurrency=100`, `requests=10000`, `TOOL_BUSY_MS=500`) are:

```csv
timestamp,url,format,concurrency,requests,errors,total_time_s,throughput_rps,p50_ms,p95_ms,p99_ms,mean_ms
2026-08-31T07:32:20.021509,http://localhost:8001/run,tool,100,10000,0,24.3701,410.3394,230.5633,276.1114,282.1203,240.7951
2026-08-31T07:37:02.853710,http://localhost:8001/run,tool,100,10000,0,24.3069,411.4053,238.2402,277.0541,284.7655,239.4947
```

The system remained stable in the clean runs, with nearly zero errors and a stable p95 around 276-277 ms.

## Interpretation

This experiment shows that:

- tool-layer CPU pressure can be detected by HPA
- the autoscaler can scale the tool tier independently
- the synthetic tool workload can remain stable once it is tuned to a moderate operating point

However, the measured throughput and p95 did not show a strong improvement in this specific configuration. This is an important limitation: the tuned workload is near the operating boundary rather than a clearly under-provisioned regime.

In other words, the experiment supports the claim of tool-layer autoscaling feasibility, but it does not yet claim a strong performance gain under the exact current synthetic workload.

## What this proves

This is the main empirical conclusion:

- The decoupled tool service can be independently scaled under CPU pressure.
- HPA responds to tool-layer CPU utilization without requiring the agent layer to scale together.

This is the key architectural value of the decoupled design: the bottleneck can be isolated and handled at the tool tier.

## What this does not prove

This workload is synthetic and intentionally simplified; it is not a full production workload benchmark. It does not yet demonstrate a dramatic end-to-end throughput improvement under all conditions. The current evidence supports autoscaling feasibility and isolation, not general performance superiority over a monolithic architecture.

## Conclusion

The most defensible interpretation is:

- HPA does trigger on tool-layer CPU pressure,
- the tool service can scale independently,
- and the current synthetic workload is stable enough to validate this behavior.

The experiment is therefore strongest when presented as a proof of decoupled tool-layer scalability, not as a universal claim that the decoupled architecture is always faster than a monolithic design.
