"""Security audit (QA gate, PRD §9): no secrets or paid-key material in the
repo; free-tier compliance assertions.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
             ".pytest_cache", "mlruns", ".mypy_cache", ".ruff_cache"}
SCAN_EXT = {".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".toml",
            ".ini", ".cfg", ".sql", ".md", ".txt"}

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key_block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "stripe_live": re.compile(r"[sr]k_live_[0-9a-zA-Z]{16,}"),
    "supabase_service_jwt": re.compile(r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.eyJ[a-zA-Z0-9_-]{20,}"),
    "generic_secret_assignment": re.compile(
        r"(?i)(password|secret|api[_-]?key)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
}


def _scannable_files():
    for path in ROOT.rglob("*"):
        if path.is_dir() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in SCAN_EXT:
            continue
        if path.name == "test_security_audit.py":
            continue  # the scanner must not match its own pattern strings
        yield path


def test_no_secret_patterns_in_repo():
    findings = []
    allowlist_markers = ("your-", "change-me", "test-secret", "integration-secret",
                         "dev-anon-key", "dev-jwt-secret", "example", "placeholder",
                         "SUPABASE_JWT_SECRET", "JWT_SECRET", "API_KEY")
    for path in _scannable_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            for m in pattern.finditer(text):
                line = text[max(0, m.start() - 60):m.end() + 20]
                if any(marker in line for marker in allowlist_markers):
                    continue
                findings.append(f"{path.relative_to(ROOT)}: {name}: {line.strip()[:80]}")
    assert not findings, "Potential secrets found:\n" + "\n".join(findings)


def test_env_files_not_committable():
    gitignore = (ROOT / ".gitignore").read_text()
    assert ".env" in gitignore
    # No actual .env file may exist in the repo (only templates).
    env_files = [p for p in ROOT.rglob(".env") if ".git" not in p.parts]
    assert not env_files, f"Committed .env found: {env_files}"


def test_env_templates_have_no_real_values():
    for template in [ROOT / "infra" / "env.example", ROOT / "frontend" / ".env.example"]:
        if not template.exists():
            continue
        for line in template.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if any(s in key for s in ("KEY", "SECRET", "PASSWORD")):
                assert not value or value.startswith("your-"), \
                    f"{template.name}: {key} has a real-looking value"


def test_no_paid_api_endpoints():
    """QA free-tier compliance: scan for known paid-only API hosts."""
    paid_hosts = ("api.bloomberg.com", "refinitiv", "api.predicthq.com",
                  "poligon.io-paid", "sp-api.amazon.com")
    for path in _scannable_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for host in paid_hosts:
            assert host not in text, f"{path.relative_to(ROOT)} references {host}"
