from unittest.mock import MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from slack_dumper.client import MAX_RETRIES, SlackClient


def _make_client(token="xoxp-test"):
    return SlackClient(token)


def test_paginate_single_page():
    client = _make_client()
    mock_resp = {
        "channels": [{"id": "C1"}, {"id": "C2"}],
        "response_metadata": {"next_cursor": ""},
    }
    with patch.object(client._client, "conversations_list", return_value=mock_resp):
        results = list(client.paginate("conversations_list", "channels"))
    assert len(results) == 2


def test_call_retries_on_rate_limit():
    client = _make_client()
    error_resp = MagicMock(status_code=429, headers={"Retry-After": "0"})
    ok_resp = {"ok": True, "channels": []}
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise SlackApiError("rate limited", error_resp)
        return ok_resp

    with patch.object(client._client, "conversations_list", side_effect=side_effect):
        result = client.call("conversations_list")
    assert call_count == 2
    assert result["ok"] is True


def test_paginate_multiple_pages():
    """다중 페이지 pagination이 올바르게 합쳐지는지 검증"""
    client = _make_client()
    page1 = {
        "channels": [{"id": "C1"}],
        "response_metadata": {"next_cursor": "cursor-abc"},
    }
    page2 = {
        "channels": [{"id": "C2"}],
        "response_metadata": {"next_cursor": ""},
    }
    responses = [page1, page2]
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        result = responses[call_count]
        call_count += 1
        return result

    with patch.object(client._client, "conversations_list", side_effect=side_effect):
        results = list(client.paginate("conversations_list", "channels"))
    assert len(results) == 2
    assert call_count == 2


def test_call_raises_non_rate_limit_errors():
    """429가 아닌 SlackApiError는 즉시 re-raise되어야 함"""
    client = _make_client()
    error_resp = MagicMock(status_code=403, headers={})

    def side_effect(**kwargs):
        raise SlackApiError("not_authed", error_resp)

    with patch.object(client._client, "conversations_list", side_effect=side_effect):
        with pytest.raises(SlackApiError):
            client.call("conversations_list")


def test_call_raises_after_max_retries():
    """MAX_RETRIES 초과 시 마지막 SlackApiError를 raise해야 함"""
    client = _make_client()
    error_resp = MagicMock(status_code=429, headers={"Retry-After": "0"})
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        raise SlackApiError("rate limited", error_resp)

    with patch.object(client._client, "conversations_list", side_effect=side_effect):
        with pytest.raises(SlackApiError):
            client.call("conversations_list")
    assert call_count == MAX_RETRIES
