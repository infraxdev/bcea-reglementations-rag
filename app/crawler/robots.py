from __future__ import annotations

import asyncio
from urllib import robotparser

import httpx

from .utils import domain_of


class RobotsCache:
    """Fetches and caches robots.txt per-domain, one fetch per domain per crawl."""

    def __init__(self, user_agent: str, client: httpx.AsyncClient):
        self._user_agent = user_agent
        self._client = client
        self._parsers: dict[str, robotparser.RobotFileParser] = {}
        self._lock = asyncio.Lock()

    async def _get_parser(self, url: str) -> robotparser.RobotFileParser:
        domain = domain_of(url)
        async with self._lock:
            cached = self._parsers.get(domain)
            if cached is not None:
                return cached

            parser = robotparser.RobotFileParser()
            scheme = url.split("://", 1)[0]
            robots_url = f"{scheme}://{domain}/robots.txt"
            try:
                resp = await self._client.get(robots_url, timeout=10)
                if resp.status_code < 400:
                    parser.parse(resp.text.splitlines())
                else:
                    parser.parse([])
            except Exception:
                parser.parse([])
            self._parsers[domain] = parser
            return parser

    async def can_fetch(self, url: str) -> bool:
        parser = await self._get_parser(url)
        try:
            return parser.can_fetch(self._user_agent, url)
        except Exception:
            return True
