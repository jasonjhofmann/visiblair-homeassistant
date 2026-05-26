"""Shared pytest fixtures for the VisiblAir test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sensor_response_raw() -> str:
    """The captured (and credential-redacted) live API payload, as a string.

    Tests should parse this with the same defensive parser the integration
    uses — exercising end-to-end means hitting both the JSON parse step
    *and* the nested ``lastSampleDataRedis`` decode.
    """
    return (FIXTURES / "sensor_response.json").read_text()


@pytest.fixture
def sensor_response_dict(sensor_response_raw: str) -> dict[str, Any]:
    """The same payload parsed to a Python dict."""
    return json.loads(sensor_response_raw)
