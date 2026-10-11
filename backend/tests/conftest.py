import os

# models.py binds its engine at import time, so the test database has to be
# selected before anything imports it — the background workflow task opens its
# own SessionLocal and must land on this same file.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from models import Base, engine, SessionLocal
from main import app, get_db
import main


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    # Both registries are module globals keyed by the primary key, and the table is
    # rebuilt for every test, so ids repeat. A leftover entry makes one test's run
    # send its frames into the previous test's socket.
    main.active_connections.clear()
    main.running_tasks.clear()
    yield
    Base.metadata.drop_all(bind=engine)
    main.active_connections.clear()
    main.running_tasks.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
