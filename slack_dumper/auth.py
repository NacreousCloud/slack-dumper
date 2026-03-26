import os

from dotenv import load_dotenv

load_dotenv()


def load_token() -> str:
    token = os.environ.get("SLACK_USER_TOKEN", "")
    if not token.startswith("xoxp-"):
        raise ValueError(
            "SLACK_USER_TOKEN이 설정되지 않았거나 user token이 아닙니다. "
            "'xoxp-'로 시작해야 합니다."
        )
    return token
