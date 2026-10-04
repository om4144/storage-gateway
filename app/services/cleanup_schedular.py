import asyncio
from datetime import datetime, timezone
from sqlmodel import Session, select

from app.db.models import ObjectRecord
from app.services.object_store import ObjectStore

async def cleanup_expired_objects(engine):
    """
    Background task that periodically checks for expired objects
    and removes them from the database.
    """
    while True:
        try:
            now = datetime.now(timezone.utc)
            with Session(engine) as session:
                statement = select(ObjectRecord).where(ObjectRecord.expire_at < now)
                expired_records = session.exec(statement).all()

                if expired_records:
                    for record in expired_records:
                        store = ObjectStore()
                        await store.delete(session= session, object_id= record.object_id , key= record.key)

        except Exception as e:
            print(f"Error during cleanup cycle: {e}")

        await asyncio.sleep(3600)

def start_cleanup_task(engine):
    """
    Helper to launch the cleanup loop as a background task.
    """
    asyncio.create_task(cleanup_expired_objects(engine))
