import pytest

from database.core import get_connection, initialize


@pytest.fixture
def db():
    conn = get_connection(":memory:")
    initialize(conn)
    yield conn
    conn.close()
