from app.agent_orchestrator import AGENTS, classify_intent


def test_router_sends_price_question_to_product_price_and_verifier():
    plan = classify_intent("Chi mi vende meglio i bomboloni e qual è il prezzo medio?")
    assert plan[:2] == ["products", "prices"]
    assert plan[-2:] == ["verifier", "answer"]


def test_router_sends_review_question_to_reviews():
    plan = classify_intent("Quali sono le camere con le recensioni peggiori?")
    assert plan[0] == "reviews"
    assert "products" not in plan


def test_agent_registry_is_small_and_specialized():
    assert {"router", "products", "classifier", "invoices", "prices", "reviews", "verifier", "answer"} == set(AGENTS)
    assert all(spec.tools for spec in AGENTS.values())


def test_agent_registry_endpoint(client):
    response = client.get("/api/eye/agents/registry")
    assert response.status_code == 200
    payload = response.json()
    assert any(x["name"] == "verifier" for x in payload)
    assert any(x["name"] == "products" for x in payload)
