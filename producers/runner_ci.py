"""CI-mode producer runner (serverless mode, decision 027).

Runs ONE cycle and exits — designed for GitHub Actions cron. Producer config
is built from Supabase (profiles, signal_settings, product categories), so
any signed-up user's signals are fetched without a static config file.
"""
import logging
import os
import tempfile

from runner import build_producers, run_cycle
from shared.cache import DiskCache
from shared.supabase_pub import SupabasePublisher

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("runner_ci")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Trends keyword quota: 1 keyword per category (pytrends throttling budget).
TRENDS_KEYWORDS_PER_CATEGORY = 1


def build_config_from_supabase(client) -> dict:
    """Assemble the producer config from live user data."""
    profiles = (
        client.table("profiles")
        .select("id,country_code,latitude,longitude,timezone")
        .execute().data
    )
    settings = (
        client.table("signal_settings").select("user_id,signal,enabled")
        .execute().data
    )
    products = (
        client.table("products").select("user_id,category").execute().data
    )

    enabled = {r["signal"] for r in settings if r.get("enabled")}
    locations = [
        {"user_id": p["id"], "latitude": p["latitude"], "longitude": p["longitude"],
         "timezone": p.get("timezone") or "UTC"}
        for p in profiles
        if p.get("latitude") is not None and p.get("longitude") is not None
    ]
    country_codes = sorted({p["country_code"] for p in profiles if p.get("country_code")})
    geo_by_user = {p["id"]: p.get("country_code", "") for p in profiles}

    category_keywords: dict[str, list[str]] = {}
    for row in products:
        cat = (row.get("category") or "").strip()
        if not cat:
            continue
        key = f"{row['user_id']}:{cat}"
        category_keywords.setdefault(key, [])
        if cat not in category_keywords[key]:
            category_keywords[key].append(cat)
    category_keywords = {
        k: v[:TRENDS_KEYWORDS_PER_CATEGORY] for k, v in category_keywords.items()
    }

    return {
        "enabled_signals": sorted(enabled),
        "locations": locations,
        "country_codes": country_codes,
        "category_keywords": category_keywords,
        "geo_by_user": geo_by_user,
        "series": ["CPIAUCSL", "UMCSENT", "UNRATE", "PCE"],
        "asins_by_user": {},  # marketplace deferred (decision 025)
    }


def main() -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")

    from supabase import create_client

    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    publisher = SupabasePublisher(client)
    # CI runners are ephemeral; the disk cache survives only within a run,
    # which is fine — freshness is tracked via signal_status in Supabase.
    cache = DiskCache(os.environ.get("CACHE_DIR", tempfile.mkdtemp()))

    config = build_config_from_supabase(client)
    logger.info("config: signals=%s locations=%d countries=%s categories=%d",
                config["enabled_signals"], len(config["locations"]),
                config["country_codes"], len(config["category_keywords"]))

    # Reuse the production cycle logic verbatim.
    run_cycle(publisher, cache, config)
    logger.info("producer cycle complete")


if __name__ == "__main__":
    main()
