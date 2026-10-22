"""Request hardening: pb string escaping, Google-only hosts, a private cookie file."""

from __future__ import annotations

import json
import os
import stat
from urllib.parse import unquote

import httpx
import pytest

from gmaps._auth.session import CookieSession
from gmaps._search import SearchAPI, _build_search_url
from gmaps.exceptions import HostNotAllowedError
from gmaps.transport import HTTPTransport


def _pb(url: str) -> str:
    return unquote(url.split("&pb=", 1)[1])


def test_search_text_cannot_add_pb_fields():
    url = _build_search_url("cafe!7i500!8i40", 48.2, 16.37)
    pb = _pb(url)
    assert pb.startswith("!1scafe*217i500*218i40!4m8")  # one string field, no injected !7i/!8i
    assert "&q=cafe%217i500%218i40&" in url  # the plain q= parameter stays URL-encoded only


class RecordingTransport:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def get(self, path: str, **kwargs):
        self.paths.append(path)
        return None


async def test_place_details_strings_cannot_add_pb_fields():
    transport = RecordingTransport()
    api = SearchAPI(transport)  # type: ignore[arg-type]
    await api.place_details("ChIJ!x", "0x1:0x2", "/g/!y", "d!z", "Bar! *Two", query="q!w")
    pb = unquote(transport.paths[0].split("&pb=", 1)[1].split("&q=", 1)[0])
    for injected in ("!x", "!y", "!z", "!w", "! *"):
        assert injected not in pb, injected
    assert "!5sChIJ*21x!6sq*21w" in pb and "!39sBar*21 *2ATwo!40b1" in pb


async def test_redirects_to_other_hosts_are_refused():
    sent = []

    def handler(request):
        sent.append(request.url.host)
        if request.url.host == "www.google.com":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        return httpx.Response(200, text="[]")

    transport = HTTPTransport(
        base_url="https://www.google.com", max_retries=3, retry_delay=0.0, min_delay=0.0
    )
    from gmaps._hosts import refuse_other_hosts

    transport._client = httpx.AsyncClient(
        base_url="https://www.google.com",
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        event_hooks={"request": [refuse_other_hosts]},
    )
    try:
        with pytest.raises(HostNotAllowedError):
            await transport.get("/maps/x", response_type="json")
    finally:
        await transport.close()
    assert sent == ["www.google.com"]  # the redirect target was never contacted, and no retries


async def test_real_clients_carry_the_host_guard():
    from gmaps._hosts import refuse_other_hosts

    transport = HTTPTransport(base_url="https://www.google.com")
    await transport.open()
    try:
        assert refuse_other_hosts in transport.client.event_hooks["request"]
    finally:
        await transport.close()
    session = CookieSession()
    await session._init_client()
    try:
        assert refuse_other_hosts in session._client.event_hooks["request"]  # type: ignore[union-attr]
    finally:
        await session.__aexit__()


def test_cookie_file_is_private_and_atomic(tmp_path):
    target = tmp_path / "state" / "cookies.json"
    session = CookieSession(cookie_file=str(target))
    session._cookies = {"NID": "n", "AEC": "a", "SOCS": "s"}
    session._save_to_file()
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert not [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]
    # A symlink planted at the path is replaced, not followed.
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("keep")
    target.unlink()
    target.symlink_to(elsewhere)
    session._save_to_file()
    assert elsewhere.read_text() == "keep" and not target.is_symlink()


def test_cookie_file_loads_only_consent_cookies(tmp_path):
    import time

    target = tmp_path / "cookies.json"
    target.write_text(
        json.dumps(
            {
                "cookies": {"NID": "n", "AEC": "a", "SOCS": "s", "SID": "account", "HSID": 1},
                "saved_at": time.time(),
            }
        )
    )
    session = CookieSession(cookie_file=str(target))
    session._load_from_file()
    assert session.cookies == {"NID": "n", "AEC": "a", "SOCS": "s"}
    for bad in ("[1, 2]", '{"cookies": "x"}', "not json"):
        target.write_text(bad)
        other = CookieSession(cookie_file=str(target))
        other._load_from_file()
        assert other.cookies == {}
