import os

from dotenv import load_dotenv


def load_token() -> str:
    load_dotenv()
    token = os.environ.get("SLACK_TOKEN", "")
    if not (token.startswith("xoxp-") or token.startswith("xoxc-")):
        raise ValueError(
            "SLACK_TOKEN이 설정되지 않았거나 올바르지 않습니다. "
            "'xoxp-' 또는 'xoxc-'로 시작해야 합니다."
        )
    return token


def load_cookie() -> str | None:
    """xoxc- 토큰 사용 시 파일 다운로드에 필요한 d= 쿠키 값을 반환"""
    load_dotenv()
    return os.environ.get("SLACK_COOKIE")
