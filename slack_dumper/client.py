import logging
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackClient:
    def __init__(self, token: str):
        self._client = WebClient(token=token)

    def call(self, method: str, **kwargs):
        """rate limit(429) 시 자동 대기 후 재시도"""
        while True:
            try:
                fn = getattr(self._client, method)
                return fn(**kwargs)
            except SlackApiError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    logger.warning("Rate limited. Waiting %ds...", retry_after)
                    time.sleep(retry_after)
                else:
                    raise

    def paginate(self, method: str, result_key: str, **kwargs):
        """cursor 기반 페이지네이션 제너레이터"""
        cursor = None
        while True:
            resp = self.call(method, cursor=cursor, limit=200, **kwargs)
            yield from resp[result_key]
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
