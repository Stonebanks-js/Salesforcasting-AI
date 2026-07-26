"""Nightly orchestration: bronze -> silver -> gold -> (train/infer in Phase 10)
-> publish. Idempotent jobs: a missed night simply catches up on the next run
(architecture.md §6 risk mitigation).
"""
import subprocess
import sys
import time

JOBS = [
    "jobs.bronze_ingest",
    "jobs.silver_transform",
    "jobs.gold_features",
    "ml.train",
    "ml.infer",
    "jobs.publish_to_supabase",
    "jobs.health_sync",
]


def main() -> None:
    for job in JOBS:
        print(f"[nightly] starting {job}", flush=True)
        start = time.time()
        result = subprocess.run(
            [sys.executable, "-m", job.replace("/", ".")],
            check=False,
        )
        elapsed = time.time() - start
        if result.returncode != 0:
            # Degrade, don't halt: publish/health still run so the dashboard
            # reflects reality (NFR-3).
            print(f"[nightly] {job} FAILED (code {result.returncode}) after {elapsed:.0f}s", flush=True)
        else:
            print(f"[nightly] {job} ok in {elapsed:.0f}s", flush=True)


if __name__ == "__main__":
    main()
