import pytest
from fastapi.testclient import TestClient

from app.main import app


# Provides a TestClient with clean dependency overrides so each test drives the app without real services.
@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
