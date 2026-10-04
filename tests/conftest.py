import pytest
from fastapi.testclient import TestClient

from engine.api.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
