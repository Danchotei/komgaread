import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def test_app_version_matches_package_metadata():
    expected = json.loads((Path(__file__).resolve().parents[2] / "package.json").read_text(encoding="utf-8"))["version"]
    client = TestClient(main.app)
    assert client.get("/api/version").json() == {"version": expected}
    assert client.get("/openapi.json").json()["info"]["version"] == expected
