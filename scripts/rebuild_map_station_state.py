from __future__ import annotations

from app.db import init_db
from app.services.map_station_state import rebuild_map_station_state


if __name__ == "__main__":
    init_db()
    result = rebuild_map_station_state(force=True)
    print(f"map_station_state rebuilt: {result['station_count']} stations, revision {result['revision']}")
