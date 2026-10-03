from fastapi.testclient import TestClient

from src.api import create_app, get_matcher


def make_client():
    get_matcher.cache_clear()
    return TestClient(create_app())


def test_health_describes_local_vector_backend(monkeypatch):
    monkeypatch.setenv("POPSIGN_DATA_BACKEND", "local")
    monkeypatch.setenv("POPSIGN_EMBEDDING_PROVIDER", "hashing")
    client = make_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data_backend"] == "local"
    assert payload["dimensions"] == 768


def test_match_endpoint_returns_video_and_diagnostics(monkeypatch):
    monkeypatch.setenv("POPSIGN_DATA_BACKEND", "local")
    monkeypatch.setenv("POPSIGN_EMBEDDING_PROVIDER", "hashing")
    client = make_client()

    response = client.post(
        "/api/match",
        json={"phrase": "She opened a can of soup.", "target_word": "can"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["selected_video_key"] == "demo/can/container.mp4"
    assert payload["top_score"] > payload["runner_up_score"]


def test_demo_story_exercises_all_pilot_words(monkeypatch):
    monkeypatch.setenv("POPSIGN_DATA_BACKEND", "local")
    client = make_client()

    response = client.post(
        "/api/stories/demo",
        json={"prompt": "A child cooks dinner.", "difficulty": "Level A"},
    )

    assert response.status_code == 200
    pages = response.json()["pages"]
    assert len(pages) == 6
    assert {page["target_word"] for page in pages} == {"about", "can", "love"}


def test_frontend_is_served(monkeypatch):
    monkeypatch.setenv("POPSIGN_DATA_BACKEND", "local")
    client = make_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "Generate Story" in response.text
    assert "Maya Makes Dinner" in response.text
