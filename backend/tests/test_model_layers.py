from app.model_layers import (
    AiRuntime,
    is_model_present,
    pick_model_sequence,
    should_escalate,
)


def _runtime(policy: str = "fast_first") -> AiRuntime:
    return AiRuntime(
        ollama_url="http://127.0.0.1:11434",
        chat_model_fast="llama3.2:3b",
        chat_model_quality="qwen3:8b",
        embedding_model="qwen3-embedding:0.6b",
        policy=policy,
    )


def test_is_model_present_matches_exact_and_prefix():
    installed = ["llama3.2:3b", "qwen3:8b"]
    assert is_model_present(installed, "llama3.2:3b")
    assert is_model_present(installed, "qwen3:8b")
    assert not is_model_present(installed, "mistral:7b")


def test_fast_first_sequence_prefers_office_mirror():
    seq = pick_model_sequence(_runtime("fast_first"), ["llama3.2:3b", "qwen3:8b"])
    assert seq == [("fast", "llama3.2:3b"), ("quality", "qwen3:8b")]


def test_fast_only_never_escalates():
    seq = pick_model_sequence(_runtime("fast_only"), ["llama3.2:3b", "qwen3:8b"])
    assert seq == [("fast", "llama3.2:3b")]


def test_quality_policy_uses_quality_model():
    seq = pick_model_sequence(_runtime("quality"), ["llama3.2:3b", "qwen3:8b"])
    assert seq == [("quality", "qwen3:8b")]


def test_degrades_when_preferred_missing():
    assert pick_model_sequence(_runtime("fast_first"), ["qwen3:8b"]) == [("quality", "qwen3:8b")]
    assert pick_model_sequence(_runtime("quality"), ["llama3.2:3b"]) == [("fast", "llama3.2:3b")]


def test_escalate_only_on_low_confidence_with_more_layers():
    assert should_escalate({"answer": "ok", "confidence": "high"}, has_more=True, policy="fast_first") is False
    assert should_escalate({"answer": "ok", "confidence": "low"}, has_more=True, policy="fast_first") is True
    assert should_escalate({"answer": "", "confidence": "medium"}, has_more=True, policy="fast_first") is True
    assert should_escalate({"answer": "", "confidence": "low"}, has_more=False, policy="fast_first") is False
    assert should_escalate({"answer": "ok", "confidence": "low"}, has_more=True, policy="fast_only") is False
