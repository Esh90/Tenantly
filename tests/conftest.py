import os

os.environ["TENANTLY_STORE"] = "fixture"  # contract tests run on fixtures
# tests never reach a paid or free model service, whatever .env holds
os.environ["GROQ_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
import pytest
from fastapi.testclient import TestClient

from engine.api.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
