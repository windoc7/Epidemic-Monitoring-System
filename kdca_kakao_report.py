#!/usr/bin/env python
"""
Send the latest KDCA weekly infectious disease sentinel surveillance report to KakaoTalk.

Configuration is read from config.json in this directory by default.
Set KDCA_KAKAO_CONFIG to point at another config file.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_STATE = BASE_DIR / "state.json"


KDCA_LIST_URL = (
    "https://dportal.kdca.go.kr/pot/bbs/BD_selectBbsList.do?"
    "q_bbsDocNo=&q_bbsSn=1010&q_clsfNo=2&q_currPage=1&"
    "q_searchKeyTy=&q_searchVal=%ED%91%9C%EB%B3%B8%EA%B0%90%EC%8B%9C&"
    "q_sortName=q_sortOrder%3D"
)


@dataclass(frozen=True)
class Report:
    doc_no: str
    title: str
    department: str
    published_date: str
    url: str


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    env_map = {
        "KAKAO_REST_API_KEY": "kakao_rest_api_key",
        "KAKAO_REFRESH_TOKEN": "kakao_refresh_token",
        "KAKAO_CLIENT_SECRET": "kakao_client_secret",
        "KDCA_LIST_URL": "kdca_list_url",
        "STATE_PATH": "state_path",
    }
    for env_name, config_key in env_map.items():
        value = os.environ.get(env_name)
        if value:
            config[config_key] = value
    if "VERIFY_SSL" in os.environ:
        config["verify_ssl"] = env_bool("VERIFY_SSL")
    if "DISABLE_STATE" in os.environ:
        config["disable_state"] = env_bool("DISABLE_STATE")
    return config


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def hangul_count(value: str) -> int:
    return sum("\uac00" <= char <= "\ud7a3" for char in value)


def repair_mojibake(value: str) -> str:
    """Repair UTF-8 Korean text that was accidentally decoded as CP949."""
    try:
        repaired = value.encode("cp949").decode("utf-8")
    except UnicodeError:
        return value
    return repaired if hangul_count(repaired) > hangul_count(value) else value


def decode_response(response: Any) -> str:
    body = response.read()
    charset = response.headers.get_content_charset()
    candidates = [charset, "utf-8", "cp949", "euc-kr"]
    for candidate in dict.fromkeys(filter(None, candidates)):
        try:
            return repair_mojibake(body.decode(candidate))
        except UnicodeError:
            continue
    return body.decode("utf-8", errors="replace")


def request_text(
    url: str,
    *,
    data: dict[str, str] | None = None,
    token: str | None = None,
    verify_ssl: bool = False,
) -> str:
    encoded_data = None
    headers = {
        "User-Agent": "Mozilla/5.0 kdca-weekly-report-monitor/1.0",
    }

    if data is not None:
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"

    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=encoded_data, headers=headers)
    context = None if verify_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return decode_response(response)


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def report_url(doc_no: str) -> str:
    query = urllib.parse.urlencode(
        {
            "q_bbsDocNo": doc_no,
            "q_bbsSn": "1010",
            "q_clsfNo": "2",
        }
    )
    return f"https://dportal.kdca.go.kr/pot/bbs/BD_selectBbs.do?{query}"


def parse_title(text: str) -> str | None:
    match = re.search(r"(20\d{2}\s*년?\s*감염병\s*표본감시\s*주간소식지\s*\d+\s*주차)", text)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def fallback_title(published_date: str) -> str:
    return f"감염병 표본감시 주간소식지 ({published_date})"


def find_latest_report(list_html: str) -> Report:
    list_html = repair_mojibake(list_html)
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", list_html, flags=re.IGNORECASE | re.DOTALL)
    fallback_doc_numbers = re.findall(r"q_bbsDocNo=(\d+)", list_html)

    for row in rows:
        text = repair_mojibake(strip_tags(row))
        if "감염병" not in text or "표본감시" not in text:
            continue

        doc_match = re.search(r"q_bbsDocNo=(\d+)", row)
        if not doc_match and fallback_doc_numbers:
            doc_match = re.search(r"(\d+)", fallback_doc_numbers[0])
        if not doc_match:
            continue

        date_match = re.search(r"(20\d{2}\.\d{2}\.\d{2})", text)
        if date_match:
            published_date = date_match.group(1)
            title = parse_title(text) or fallback_title(published_date)
            doc_no = doc_match.group(1)
            return Report(
                doc_no=doc_no,
                title=title,
                department="감염병관리과" if "감염병관리과" in text else "",
                published_date=published_date,
                url=report_url(doc_no),
            )

    text = repair_mojibake(strip_tags(list_html))
    date_match = re.search(r"(20\d{2}\.\d{2}\.\d{2})", text)
    if date_match and fallback_doc_numbers:
        published_date = date_match.group(1)
        doc_no = fallback_doc_numbers[0]
        return Report(
            doc_no=doc_no,
            title=parse_title(text) or fallback_title(published_date),
            department="감염병관리과",
            published_date=published_date,
            url=report_url(doc_no),
        )

    raise RuntimeError("최신 감염병 표본감시 주간소식지를 찾지 못했습니다.")


def refresh_kakao_token(config: dict[str, Any], config_path: Path) -> str:
    rest_api_key = config.get("kakao_rest_api_key")
    refresh_token = config.get("kakao_refresh_token")
    if not rest_api_key or not refresh_token:
        raise RuntimeError("config.json에 kakao_rest_api_key와 kakao_refresh_token을 설정해 주세요.")

    payload = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if config.get("kakao_client_secret"):
        payload["client_secret"] = config["kakao_client_secret"]

    response = request_text(
        "https://kauth.kakao.com/oauth/token",
        data=payload,
        verify_ssl=bool(config.get("verify_ssl", False)),
    )
    token_data = json.loads(response)
    access_token = token_data["access_token"]

    config["kakao_access_token"] = access_token
    if token_data.get("refresh_token"):
        config["kakao_refresh_token"] = token_data["refresh_token"]
        if os.environ.get("KAKAO_REFRESH_TOKEN"):
            print("WARNING: Kakao issued a new refresh token. Update KAKAO_REFRESH_TOKEN in Railway Variables.")
    config["kakao_token_refreshed_at"] = datetime.now().isoformat(timespec="seconds")
    if config_path.exists() or not os.environ.get("KAKAO_REFRESH_TOKEN"):
        save_json(config_path, config)
    return access_token


def send_kakao_message(access_token: str, report: Report, *, verify_ssl: bool) -> None:
    message = (
        "감염병 주간 리포트\n"
        f"{report.title}\n"
        f"등록일: {report.published_date}\n"
        "질병관리청 감염병포털에 최신 주간소식지가 올라왔습니다.\n"
        "아래 버튼에서 원문을 확인하세요."
    )
    template_object = {
        "object_type": "text",
        "text": message[:190],
        "link": {
            "web_url": report.url,
            "mobile_web_url": report.url,
        },
        "button_title": "리포트 보기",
    }

    response = request_text(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        data={"template_object": json.dumps(template_object, ensure_ascii=False)},
        token=access_token,
        verify_ssl=verify_ssl,
    )
    result = json.loads(response)
    if result.get("result_code") != 0:
        raise RuntimeError(f"카카오톡 메시지 전송 실패: {response}")


def run(config_path: Path, *, dry_run: bool, force: bool) -> int:
    config = load_config(config_path)
    state_path = Path(config.get("state_path", DEFAULT_STATE))
    disable_state = bool(config.get("disable_state", False))
    state = {} if disable_state else load_json(state_path)

    list_url = config.get("kdca_list_url", KDCA_LIST_URL)
    verify_ssl = bool(config.get("verify_ssl", False))
    latest_report = find_latest_report(request_text(list_url, verify_ssl=verify_ssl))

    print(f"Latest report: {latest_report.title} ({latest_report.published_date})")
    print(latest_report.url)

    already_sent = not disable_state and state.get("last_sent_doc_no") == latest_report.doc_no
    if already_sent and not force:
        print("No new report. Skipping KakaoTalk message.")
        return 0

    if dry_run:
        print("Dry run only. KakaoTalk message was not sent.")
        return 0

    access_token = refresh_kakao_token(config, config_path)
    send_kakao_message(access_token, latest_report, verify_ssl=verify_ssl)

    if not disable_state:
        state.update(
            {
                "last_sent_doc_no": latest_report.doc_no,
                "last_sent_title": latest_report.title,
                "last_sent_url": latest_report.url,
                "last_sent_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        save_json(state_path, state)
    print("KakaoTalk message sent.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Send KDCA weekly report to KakaoTalk.")
    parser.add_argument("--config", default=os.environ.get("KDCA_KAKAO_CONFIG", str(DEFAULT_CONFIG)))
    parser.add_argument("--dry-run", action="store_true", help="Fetch the latest report without sending KakaoTalk.")
    parser.add_argument("--force", action="store_true", help="Send even if this report was already sent.")
    args = parser.parse_args()

    try:
        return run(Path(args.config), dry_run=args.dry_run, force=args.force or env_bool("FORCE_SEND"))
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
