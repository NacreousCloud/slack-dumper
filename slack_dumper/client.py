import logging
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


class SlackClient:
    def __init__(self, token: str):
        self._client = WebClient(token=token)

    def call(self, method: str, **kwargs):
        """rate limit(429) 시 자동 대기 후 재시도. 최대 MAX_RETRIES회."""
        for attempt in range(MAX_RETRIES):
            try:
                fn = getattr(self._client, method)
                return fn(**kwargs)
            except SlackApiError as e:
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    retry_after = int(float(e.response.headers.get("Retry-After", 1)))
                    logger.warning(
                        "Rate limited. Waiting %ds... (attempt %d/%d)",
                        retry_after,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    time.sleep(retry_after)
                else:
                    raise

    def paginate(self, method: str, result_key: str, **kwargs):
        """cursor 기반 페이지네이션 제너레이터"""
        kwargs.setdefault("limit", 200)
        cursor = None
        while True:
            resp = self.call(method, cursor=cursor, **kwargs)
            if result_key not in resp:
                raise KeyError(
                    f"'{result_key}' not found in response from '{method}'. "
                    f"Keys: {list(resp.keys())}"
                )
            yield from resp[result_key]
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
