from datetime import datetime, timezone
from app.db.database import database


async def update_user_last_login(user_id: int) -> None:
    query = "UPDATE users SET last_login = :last_login WHERE id = :user_id"
    values = {"last_login": datetime.now(timezone.utc), "user_id": user_id}
    await database.execute(query=query, values=values)