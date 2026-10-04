import os

os.environ["TENANTLY_STORE"] = "fixture"  # contract tests run on fixtures
import pytest
from fastapi.testclient import TestClient

from engine.api.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
