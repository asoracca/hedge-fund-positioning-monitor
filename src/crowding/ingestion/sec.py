"""SEC public sources. Single-process shared limiter; coordinate across workers."""

import hashlib
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlparse
import httpx


class SECClient:
    _lock = threading.Lock()
    _last_request = 0.0

    def __init__(self, user_agent=None, cache="data/cache", transport=None):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT", "")
        if "@" not in self.user_agent or "example." in self.user_agent:
            raise ValueError("Set SEC_USER_AGENT to your name and real contact email")
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=60,
            transport=transport,
            follow_redirects=False,
        )

    def close(self):
        self.client.close()

    def get(self, url, refresh=False):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"www.sec.gov", "data.sec.gov"}:
            raise ValueError("Only HTTPS SEC endpoints allowed")
        key = hashlib.sha256(url.encode()).hexdigest()
        target = self.cache / (key + ".bin")
        meta = self.cache / (key + ".json")
        if target.exists() and meta.exists() and not refresh:
            data = target.read_bytes()
            if hashlib.sha256(data).hexdigest() != json.loads(meta.read_text())["sha256"]:
                raise ValueError("Cache integrity check failed")
            return data
        for attempt in range(4):
            with self._lock:
                time.sleep(max(0, 0.21 - (time.monotonic() - SECClient._last_request)))
                SECClient._last_request = time.monotonic()
                try:
                    response = self.client.get(url)
                except httpx.TransportError:
                    if attempt == 3:
                        raise
                    response = None
            if response is not None and response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                data = response.content
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(target)
                meta.write_text(
                    json.dumps(
                        {
                            "url": url,
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "retrieved_at": pd_timestamp(),
                        },
                        indent=2,
                    )
                )
                return data
            if attempt < 3:
                retry = response.headers.get("Retry-After", "") if response is not None else ""
                time.sleep(min(60, max(2**attempt, float(retry) if retry.isdigit() else 0)))
        raise RuntimeError("SEC temporarily unavailable; retry later or use cached data")

    def submissions(self, cik):
        cik = int(cik)
        return json.loads(self.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))

    def company_facts(self, cik):
        cik = int(cik)
        return json.loads(self.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"))


def pd_timestamp():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def facts_as_of(payload, cutoff):
    """Keep fact vintages; filter on public filing date, not fiscal period."""
    import pandas as pd

    rows = []
    for taxonomy, concepts in payload.get("facts", {}).items():
        for concept, details in concepts.items():
            for unit, observations in details.get("units", {}).items():
                for obs in observations:
                    if obs.get("filed") and pd.Timestamp(obs["filed"]) <= pd.Timestamp(cutoff):
                        rows.append(dict(obs, taxonomy=taxonomy, concept=concept, unit=unit))
    return pd.DataFrame(rows)
