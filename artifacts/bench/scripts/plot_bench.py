import pandas as pd
import matplotlib.pyplot as plt
import os


def load_and_agg(path):
    df = pd.read_csv(path)
    # ensure numeric
    df['concurrency'] = df['concurrency'].astype(int)
    agg = df.groupby('concurrency').agg({
        'throughput_rps': 'mean',
        'p50_ms': 'mean',
        'p95_ms': 'mean',
        'p99_ms': 'mean',
        'mean_ms': 'mean'
    }).reset_index()
    return agg


def plot_throughput(agent_df, baseline_df, outpath):
    plt.figure(figsize=(7,4))
    plt.plot(agent_df['concurrency'], agent_df['throughput_rps'], marker='o', label='agent (decoupled)')
    plt.plot(baseline_df['concurrency'], baseline_df['throughput_rps'], marker='o', label='baseline (monolithic)')
    plt.xlabel('Concurrency')
    plt.ylabel('Throughput (req/s)')
    plt.title('Throughput vs Concurrency')
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outpath)
    print('Wrote', outpath)


def plot_latency(agent_df, baseline_df, outpath):
    plt.figure(figsize=(7,4))
    plt.plot(agent_df['concurrency'], agent_df['p50_ms'], marker='o', label='p50 agent')
    plt.plot(baseline_df['concurrency'], baseline_df['p50_ms'], marker='o', label='p50 baseline')
    plt.plot(agent_df['concurrency'], agent_df['p95_ms'], marker='x', linestyle='--', label='p95 agent')
    plt.plot(baseline_df['concurrency'], baseline_df['p95_ms'], marker='x', linestyle='--', label='p95 baseline')
    plt.xlabel('Concurrency')
    plt.ylabel('Latency (ms)')
    plt.title('Latency (p50 & p95) vs Concurrency')
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outpath)
    print('Wrote', outpath)


def main():
    agent_csv = 'bench_agent.csv'
    baseline_csv = 'bench_baseline.csv'
    if not os.path.exists(agent_csv) or not os.path.exists(baseline_csv):
        print('Missing CSV files. Expected:', agent_csv, baseline_csv)
        return

    agent = load_and_agg(agent_csv)
    baseline = load_and_agg(baseline_csv)

    os.makedirs('docs', exist_ok=True)
    plot_throughput(agent, baseline, 'docs/bench_throughput.png')
    plot_latency(agent, baseline, 'docs/bench_latency.png')


if __name__ == '__main__':
    main()
