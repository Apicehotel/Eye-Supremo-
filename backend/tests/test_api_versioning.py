def test_versioned_api_facade_keeps_local_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["app"] == "Eye Supremo"


def test_versioned_eye_facade_keeps_session_authentication(client):
    response = client.get("/api/v1/eye/hotels")
    assert response.status_code == 200
