from typing import Any
import json

def _parse_json_fields(val: Any) -> list[str]:
    """Helper to safely parse JSON field arrays regardless of database driver (SQLite string vs Postgres dict/list)."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
    return []
