import asyncio
from app.db.database import database

async def main():
    await database.connect()
    rows = await database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    names = [r["name"] for r in rows]
    print("Tables:", names)
    if "leave_requests" in names:
        print("leave_requests EXISTS")
        cols = await database.fetch_all("PRAGMA table_info(leave_requests)")
        print("Columns:", [c["name"] for c in cols])
    else:
        print("leave_requests NOT FOUND")
    await database.disconnect()

asyncio.run(main())
