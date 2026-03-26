import logging
from pathlib import Path

import click

from slack_dumper.sync import run_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@click.group()
def main():
    """Slack 개인 데이터 덤퍼"""


@main.command()
@click.option("--db", default="slack.db", show_default=True, help="SQLite DB 경로")
@click.option("--files-dir", default="slack_files", show_default=True, help="파일 저장 디렉토리")
@click.option("--skip-files", is_flag=True, help="파일 다운로드 건너뜀")
@click.option("--channel", "channels", multiple=True, help="수집할 채널 ID 또는 이름 (반복 가능)")
def sync(db, files_dir, skip_files, channels):
    """슬랙 데이터 동기화"""
    run_sync(
        db_path=Path(db),
        files_dir=Path(files_dir),
        skip_files=skip_files,
        channel_filter=list(channels) or None,
    )


@main.command()
@click.option("--db", default="slack.db", show_default=True)
@click.option("--port", default=8000, show_default=True)
def serve(db, port):
    """로컬 뷰어 서버 시작"""
    import uvicorn

    from slack_dumper.viewer.app import create_app

    app = create_app(db_path=db)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
