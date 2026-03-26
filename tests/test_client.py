from unittest.mock import MagicMock, patch

from slack_sdk.errors import SlackApiError

from slack_dumper.client import SlackClient


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
