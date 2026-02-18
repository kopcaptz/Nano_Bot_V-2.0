"""Unit tests for Smart Model Router heuristics."""

from __future__ import annotations

import pytest

from nanobot.agent.model_router import get_model_for_request
from nanobot.config.schema import ModelRouterConfig, ModelRouterModelConfig


@pytest.fixture
def router_config() -> ModelRouterConfig:
    return ModelRouterConfig(
        enabled=True,
        models=[
            ModelRouterModelConfig(model_name="smart-model", litellm_params={"model": "anthropic/claude"}),
            ModelRouterModelConfig(model_name="cheap-model", litellm_params={"model": "qwen/qwen"}),
            ModelRouterModelConfig(model_name="free-model", litellm_params={"model": "openrouter/aurora"}),
        ],
    )


def test_complex_query_routes_to_smart(router_config: ModelRouterConfig) -> None:
    """Queries with 'код', 'debug', etc. -> smart-model."""
    assert get_model_for_request("напиши код на Python", False, router_config) == "smart-model"
    assert get_model_for_request("debug this bug", False, router_config) == "smart-model"
    assert get_model_for_request("ошибка в архитектуре", False, router_config) == "smart-model"
    assert get_model_for_request("fix the error in the code", False, router_config) == "smart-model"


def test_simple_short_query_routes_to_cheap(router_config: ModelRouterConfig) -> None:
    """Short queries without keywords -> cheap-model."""
    assert get_model_for_request("привет", False, router_config) == "cheap-model"
    assert get_model_for_request("как дела?", False, router_config) == "cheap-model"
    assert get_model_for_request("Hello", False, router_config) == "cheap-model"


def test_background_routes_to_free(router_config: ModelRouterConfig) -> None:
    """is_background=True -> free-model."""
    assert get_model_for_request("anything", True, router_config) == "free-model"
    assert get_model_for_request("analyze logs", True, router_config) == "free-model"


def test_disabled_config_returns_none() -> None:
    """When config disabled or None -> None."""
    cfg = ModelRouterConfig(enabled=False, models=[ModelRouterModelConfig(model_name="x", litellm_params={})])
    assert get_model_for_request("код", False, cfg) is None
    assert get_model_for_request("hi", False, None) is None


def test_long_simple_query_defaults_to_cheap(router_config: ModelRouterConfig) -> None:
    """Long query without keywords -> cheap (default)."""
    long_text = " ".join(["word"] * 60)
    assert get_model_for_request(long_text, False, router_config) == "cheap-model"
