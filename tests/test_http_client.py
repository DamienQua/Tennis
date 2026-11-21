"""Débit et mutualisation HTTP sans aucune connexion externe."""

import asyncio
from contextlib import asynccontextmanager
import importlib
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from utils.http_client import request, set_rate_limiter, shared_pane

analysis_module = importlib.import_module("core.analyze_match")


@asynccontextmanager
async def response_context(response):
    if isinstance(response, Exception):
        raise response
    yield response


@pytest.mark.asyncio
async def test_each_http_method_acquires_the_session_limiter_before_dispatch():
    session = Mock()
    limiter = Mock(acquire=AsyncMock())
    set_rate_limiter(session, limiter)
    response = Mock()

    def dispatch(*args, **kwargs):
        assert limiter.acquire.await_count == session.get.call_count + session.post.call_count
        return response_context(response)

    session.get.side_effect = dispatch
    session.post.side_effect = dispatch
    async with request(session, "GET", "https://example.invalid/read", timeout=1) as actual:
        assert actual is response
    async with request(session, "POST", "https://example.invalid/write", data={"pane": "overview"}):
        pass
    assert limiter.acquire.await_count == 2
    session.get.assert_called_once_with("https://example.invalid/read", timeout=1)
    session.post.assert_called_once_with("https://example.invalid/write", data={"pane": "overview"})


@pytest.mark.asyncio
async def test_http_retries_consume_a_token_for_each_attempt(monkeypatch):
    session = Mock()
    limiter = Mock(acquire=AsyncMock())
    set_rate_limiter(session, limiter)
    success = Mock(status=200, text=AsyncMock(return_value="<div>ready</div>"))
    attempts = iter([Mock(status=503), aiohttp.ClientConnectionError("temporary"), success])
    session.get.side_effect = lambda *args, **kwargs: response_context(next(attempts))
    monkeypatch.setattr(analysis_module.asyncio, "sleep", AsyncMock())

    assert await analysis_module.fetch_data(session, "https://example.invalid/pane") == "<div>ready</div>"
    assert session.get.call_count == 3
    assert limiter.acquire.await_count == 3


@pytest.mark.asyncio
async def test_concurrent_readers_share_one_fetch_and_cache_the_result():
    session = Mock()
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch():
        entered.set()
        await release.wait()
        return "<div>overview</div>"

    fetcher = AsyncMock(side_effect=fetch)
    first = asyncio.create_task(shared_pane(session, ("match", "overview"), fetcher))
    await entered.wait()
    second = asyncio.create_task(shared_pane(session, ("match", "overview"), fetcher))
    await asyncio.sleep(0)
    assert fetcher.await_count == 1
    release.set()
    assert await asyncio.gather(first, second) == ["<div>overview</div>"] * 2
    assert await shared_pane(session, ("match", "overview"), fetcher) == "<div>overview</div>"
    assert fetcher.await_count == 1


@pytest.mark.asyncio
async def test_cache_keys_and_authenticated_sessions_are_separate():
    first_session, second_session = Mock(), Mock()
    first = AsyncMock(return_value="first session")
    second = AsyncMock(return_value="second session")
    other_pane = AsyncMock(return_value="different pane")
    assert await shared_pane(first_session, ("1", "overview"), first) == "first session"
    assert await shared_pane(second_session, ("1", "overview"), second) == "second session"
    assert await shared_pane(first_session, ("1", "stats"), other_pane) == "different pane"
    first.assert_awaited_once()
    second.assert_awaited_once()
    other_pane.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_and_empty_panes_can_be_fetched_again():
    session = Mock()
    fetcher = AsyncMock(side_effect=[aiohttp.ClientConnectionError("temporary"), "", "ready"])
    with pytest.raises(aiohttp.ClientConnectionError):
        await shared_pane(session, ("1", "overview"), fetcher)
    assert await shared_pane(session, ("1", "overview"), fetcher) == ""
    assert await shared_pane(session, ("1", "overview"), fetcher) == "ready"
    assert await shared_pane(session, ("1", "overview"), fetcher) == "ready"
    assert fetcher.await_count == 3


@pytest.mark.asyncio
async def test_cancelling_one_reader_does_not_cancel_the_shared_fetch():
    session = Mock()
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch():
        entered.set()
        await release.wait()
        return "ready"

    fetcher = AsyncMock(side_effect=fetch)
    first = asyncio.create_task(shared_pane(session, ("1", "stats"), fetcher))
    await entered.wait()
    second = asyncio.create_task(shared_pane(session, ("1", "stats"), fetcher))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await second == "ready"
    assert fetcher.await_count == 1
