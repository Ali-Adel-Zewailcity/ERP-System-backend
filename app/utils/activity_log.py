import json
from typing import Any

from app.db.database import database
from app.schema.auth import activity_logs


async def log_activity(
    org_id: int,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    query = activity_logs.insert().values(
        org_id=org_id,
        user_id=user_id,
        module="hr",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await database.execute(query)
