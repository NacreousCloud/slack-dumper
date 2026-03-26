import pytest
import respx
import httpx

from slack_dumper.client import SlackClient, MAX_RETRIES


def _make_client(token="xoxc-test", cookie=None):
    return SlackClient(token, cookie=cookie)


@respx.mock
def test_paginate_single_page():
    client = _make_client()
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": "C1"}, {"id": "C2"}],
            "response_metadata": {"next_cursor": ""},
        })
    )
    results = list(client.paginate("conversations_list", "channels"))
    assert len(results) == 2


@respx.mock
def test_call_retries_on_rate_limit():
    client = _make_client()
    route = respx.post("https://slack.com/api/conversations.list")
    route.side_effect = [
        httpx.Response(200, json={"ok": False, "error": "ratelimited"},
                       headers={"Retry-After": "0"}),
        httpx.Response(200, json={"ok": True, "channels": []}),
    ]
    result = client.call("conversations_list")
    assert result["ok"] is True
    assert route.call_count == 2


@respx.mock
def test_paginate_multiple_pages():
    client = _make_client()
    route = respx.post("https://slack.com/api/conversations.list")
    route.side_effect = [
        httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": "C1"}],
            "response_metadata": {"next_cursor": "cursor-abc"},
        }),
        httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": "C2"}],
            "response_metadata": {"next_cursor": ""},
        }),
    ]
    results = list(client.paginate("conversations_list", "channels"))
    assert len(results) == 2
    assert route.call_count == 2


@respx.mock
def test_call_raises_non_rate_limit_errors():
    client = _make_client()
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "not_authed"})
    )
    with pytest.raises(RuntimeError, match="not_authed"):
        client.call("conversations_list")


@respx.mock
def test_call_raises_after_max_retries():
    client = _make_client()
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "ratelimited"},
                                    headers={"Retry-After": "0"})
    )
    with pytest.raises(RuntimeError):
        client.call("conversations_list")


@respx.mock
def test_cookie_header_sent():
    """xoxc- 토큰 사용 시 Cookie 헤더가 요청에 포함되어야 함"""
    client = _make_client(token="xoxc-test", cookie="d=xoxd-abc")
    route = respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={
            "ok": True, "channels": [],
            "response_metadata": {"next_cursor": ""},
        })
    )
    client.call("conversations_list")
    assert route.calls[0].request.headers.get("cookie") == "d=xoxd-abc"
