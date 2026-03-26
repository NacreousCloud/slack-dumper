import logging
import time

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
SLACK_API_BASE = "https://slack.com/api"


class SlackClient:
    """
    xoxp- (User Token) 과 xoxc- (브라우저 세션 토큰) 를 모두 지원.
    xoxc- 사용 시 cookie(d=xoxd-...) 를 함께 전달해야 함.
    """

    def __init__(self, token: str, cookie: str | None = None):
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}
        if cookie:
            self._headers["Cookie"] = cookie

    def call(self, method: str, **kwargs) -> dict:
        """Slack API 메서드 호출. rate limit(429) 시 자동 대기 후 재시도."""
        # slack_sdk 메서드명(conversations_list) → API 경로(conversations.list) 변환
        api_method = method.replace("_", ".", 1) if "_" in method else method
        url = f"{SLACK_API_BASE}/{api_method}"

        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.post(url, headers=self._headers, data=kwargs, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                if not data.get("ok"):
                    error = data.get("error", "unknown_error")
                    if error == "ratelimited":
                        retry_after = int(resp.headers.get("Retry-After", 1))
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                "Rate limited. Waiting %ds... (attempt %d/%d)",
                                retry_after, attempt + 1, MAX_RETRIES,
                            )
                            time.sleep(retry_after)
                            continue
                    raise RuntimeError(f"Slack API error [{api_method}]: {error}")

                return data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    logger.warning("Rate limited (HTTP). Waiting %ds...", retry_after)
                    time.sleep(retry_after)
                else:
                    raise

        raise RuntimeError(f"Max retries exceeded for {api_method}")

    def paginate(self, method: str, result_key: str, **kwargs):
        """cursor 기반 페이지네이션 제너레이터"""
        kwargs.setdefault("limit", 200)
        cursor = None
        while True:
            if cursor:
                kwargs["cursor"] = cursor
            resp = self.call(method, **kwargs)
            if result_key not in resp:
                raise KeyError(
                    f"'{result_key}' not found in response from '{method}'. "
                    f"Keys: {list(resp.keys())}"
                )
            yield from resp[result_key]
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
