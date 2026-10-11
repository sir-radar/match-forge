"""Manual, opt-in FotMob backend smoke check; never an automatic sync."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date

from football.providers.fotmob import FotmobClient, normalize_daily_matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    enabled = os.environ.get("MATCHFORGE_FOTMOB_ENABLED") == "true"
    response = FotmobClient(access_approved=enabled).matches_by_date(args.date)
    print(
        json.dumps(
            {
                "source": "fotmob",
                "source_sha256": response.sha256,
                "fetched_at": response.fetched_at.isoformat(),
                "observations": [row.to_dict() for row in normalize_daily_matches(response)],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
