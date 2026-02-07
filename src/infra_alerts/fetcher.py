from __future__ import annotations

import asyncio
from typing import Any

import httpx


class FetchError(Exception):
    pass


class AsyncFetcher:
    def __init__(self, timeout_seconds: float = 10.0, retries: int = 3) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AsyncFetcher:
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_text(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> str:
        response = await self._request("GET", url, headers=headers, params=params)
        return response.text

    async def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        response = await self._request("GET", url, headers=headers, params=params)
        return response.json()

    async def post_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._request("POST", url, headers=headers, json_payload=json_payload)
        return response.json()

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise FetchError("AsyncFetcher must be used as an async context manager")

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = await self._client.request(method, url, headers=headers, params=params, json=json_payload)
                if response.status_code >= 500 or response.status_code == 429:
                    raise FetchError(f"Transient HTTP status {response.status_code} for {url}")
                if response.status_code >= 400:
                    raise FetchError(f"HTTP status {response.status_code} for {url}")
                return response
            except (httpx.HTTPError, FetchError) as exc:
                last_error = exc
                if attempt == self.retries - 1:
                    break
                await asyncio.sleep(2**attempt)
        raise FetchError(str(last_error) if last_error else f"Request failed for {url}")
