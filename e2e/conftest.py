"""pytest configuration — --e2e flag, --base-url option, fixtures."""

import os
import sys
from uuid import uuid4

import aiohttp
import pytest

# Ensure the e2e/ directory is on sys.path so that test files in subdirectories
# (e.g. scenarios/) can import helpers.* and fixtures.* modules.
_e2e_root = os.path.dirname(os.path.abspath(__file__))
if _e2e_root not in sys.path:
    sys.path.insert(0, _e2e_root)


def pytest_addoption(parser):
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end integration tests",
    )
    parser.addoption(
        "--base-url",
        default="http://localhost:8080",
        help="Master API base URL (default: http://localhost:8080)",
    )
    parser.addoption(
        "--ws-url",
        default="ws://localhost:8080/ws",
        help="Master WebSocket URL (default: ws://localhost:8080/ws)",
    )
    parser.addoption(
        "--cluster-token",
        default="e2e-test-token",
        help="Cluster token for authentication (default: e2e-test-token)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: End-to-end integration test")
    config.addinivalue_line("markers", "slow: Test with extended timeout")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--e2e"):
        return  # --e2e flag given — run all tests
    skip_e2e = pytest.mark.skip(reason="use --e2e to run E2E tests")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def base_url(pytestconfig):
    return pytestconfig.getoption("--base-url")


@pytest.fixture(scope="session")
def ws_url(pytestconfig):
    return pytestconfig.getoption("--ws-url")


@pytest.fixture(scope="session")
def cluster_token(pytestconfig):
    return pytestconfig.getoption("--cluster-token")


@pytest.fixture(scope="function")
async def http_client(base_url):
    """aiohttp ClientSession — fresh per test for reliable event-loop isolation."""
    async with aiohttp.ClientSession(base_url) as session:
        yield session


@pytest.fixture(scope="function")
async def api_client(http_client, base_url, cluster_token):
    """Master REST API client — fresh per test."""
    from helpers.master_api import MasterAPI

    return MasterAPI(http_client, base_url, cluster_token)


@pytest.fixture(scope="function")
def trace_id():
    """Random trace_id for each test."""
    return str(uuid4())


@pytest.fixture(scope="function")
def msg_id():
    """Random msg_id for each test."""
    return str(uuid4())
