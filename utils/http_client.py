"""Débit HTTP partagé par session et cache des panneaux propres à cette session."""

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from weakref import WeakKeyDictionary

from aiolimiter import AsyncLimiter


@dataclass
class SessionState:
    limiter: AsyncLimiter = field(default_factory=lambda: AsyncLimiter(10, 1))
    pane_cache: OrderedDict = field(default_factory=OrderedDict)
    pane_tasks: dict = field(default_factory=dict)


_states: WeakKeyDictionary = WeakKeyDictionary()


def session_state(session: Any) -> SessionState:
    """Évite de partager cookies, cache ou tâches entre sessions/boucles asyncio."""
    if session not in _states:
        _states[session] = SessionState()
    return _states[session]


def set_rate_limiter(session: Any, limiter: AsyncLimiter) -> None:
    session_state(session).limiter = limiter


@asynccontextmanager
async def request(session: Any, method: str, url: str, **kwargs):
    """Chaque tentative HTTP consomme un jeton, y compris les reprises."""
    await session_state(session).limiter.acquire()
    # get/post conservent la compatibilité avec les doubles de test aiohttp.
    async with getattr(session, method.lower())(url, **kwargs) as response:
        yield response


async def shared_pane(session: Any, key: tuple, fetch, max_size: int = 256) -> str:
    """Une tâche par panneau en cours ; une réponse vide reste réessayable."""
    state = session_state(session)
    if key in state.pane_cache:
        state.pane_cache.move_to_end(key)
        return state.pane_cache[key]

    async def load():
        try:
            html = await fetch()
            if html:
                state.pane_cache[key] = html
                while len(state.pane_cache) > max_size:
                    state.pane_cache.popitem(last=False)
            return html
        finally:
            state.pane_tasks.pop(key, None)

    if key not in state.pane_tasks:
        state.pane_tasks[key] = asyncio.create_task(load())
    return await asyncio.shield(state.pane_tasks[key])
