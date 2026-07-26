"""Integration test harness: chains the REAL components in-process —
backend CSV loader -> Kafka events -> pipeline transforms -> ML train/infer
-> API serving -> frontend TS contract.

Path setup makes all four codebases importable (mirrors how they'd run in
their containers).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Order matters: `tests` package must resolve to backend/tests (has fakes).
for sub in (ROOT / "pipeline", ROOT / "producers", ROOT / "backend", ROOT):
    sys.path.insert(0, str(sub))

os.environ.setdefault("SUPABASE_JWT_SECRET", "integration-secret")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_ANON_KEY", "integration-anon")
os.environ.setdefault("KAFKA_ENABLED", "false")
