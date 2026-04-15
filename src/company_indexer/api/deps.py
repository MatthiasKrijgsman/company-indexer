from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from company_indexer.db import get_sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
