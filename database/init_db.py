from database.base import Base
import database.base as db


async def init_db() -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
