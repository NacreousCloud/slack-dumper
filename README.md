# Slack Dumper

개인 Slack 데이터(채널, 비공개채널, 메시지, 스레드, 파일)를 로컬에 저장하고 오프라인에서 열람하는 도구.

관리자 권한 없이 본인 계정으로 접근 가능한 채널의 데이터만 수집합니다.

## 1. Slack App 생성 및 User Token 발급

1. https://api.slack.com/apps → **Create New App** → **From scratch**
2. App Name 입력 후 워크스페이스 선택
3. **OAuth & Permissions** → **Scopes** → **User Token Scopes** 추가:
   - `channels:read`, `channels:history`
   - `groups:read`, `groups:history`
   - `im:read`, `im:history`
   - `mpim:read`, `mpim:history`
   - `users:read`
   - `files:read`
4. **Install to Workspace** 클릭 → 권한 승인
5. **OAuth Tokens** 섹션의 **User OAuth Token** (`xoxp-...`) 복사

## 2. 설정

```bash
cp .env.example .env
# .env 파일을 열어 SLACK_USER_TOKEN=xoxp-... 입력
```

## 3. 설치

```bash
pip install -e .
```

## 4. 동기화

```bash
# 전체 동기화 (메시지 + 파일)
slack-dumper sync

# 특정 채널만 (ID 또는 이름)
slack-dumper sync --channel general --channel C1234ABCD

# 파일 다운로드 제외
slack-dumper sync --skip-files

# 다른 DB 경로 지정
slack-dumper sync --db /path/to/archive.db --files-dir /path/to/files
```

## 5. 오프라인 뷰어

```bash
slack-dumper serve
```

브라우저에서 http://localhost:8000 접속

### 뷰어 기능

- 채널 목록 (공개 / 비공개 / DM 섹션 분리)
- 날짜 구분선, 연속 메시지 묶음
- 스레드 댓글 패널 (클릭으로 열기)
- 이미지 인라인 미리보기
- 채널 내 검색 / 전체 검색
- 이전 메시지 더 보기 (페이지네이션)

## 데이터 저장 위치

| 항목 | 기본 경로 |
|---|---|
| DB | `./slack.db` |
| 파일/이미지 | `./slack_files/{file_id}/{filename}` |

## 증분 동기화

`slack-dumper sync`를 반복 실행하면 마지막 동기화 이후의 새 메시지만 수집합니다.
