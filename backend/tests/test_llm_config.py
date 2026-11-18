"""LLM configuration: .env loading, env precedence, LLM_DISABLED, and the key never reaching responses."""
import os

import pytest
from dotenv import load_dotenv

from services import llm

DUMMY = "dummy-test-key-not-real"


def test_dotenv_enables_client_and_env_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"OPENROUTER_API_KEY={DUMMY}\nOPENROUTER_MODEL=test/model\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", "env/model")
    monkeypatch.delenv("LLM_DISABLED", raising=False)
    load_dotenv(env, override=False)
    try:
        assert llm.status() == (True, "")
        assert llm.model() == "env/model"          # a real env var is not overridden
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_disabled_flag_wins(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY)
    monkeypatch.setenv("LLM_DISABLED", "1")
    assert llm.status() == (False, "LLM_DISABLED")
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("s", "u")


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_DISABLED", raising=False)
    assert llm.status() == (False, "no OPENROUTER_API_KEY")


def test_reply_parsing():
    assert llm._parse('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm._parse('Sure: {"a": 2} done') == {"a": 2}
    with pytest.raises(llm.LLMUnavailable):
        llm._parse("no json here")


def test_health_never_contains_key(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY)
    body = client.get("/api/health")
    assert body.status_code == 200
    assert DUMMY not in body.text
    assert body.json()["llm"] == "disabled"     # LLM_DISABLED is set for tests
