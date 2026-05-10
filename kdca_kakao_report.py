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


@dataclass(frozen=True)
class ReportSummary:
    week: str
    influenza: str
    influenza_direction: str
    ari_cases: str
    ari_delta: str
    key_viruses: list[tuple[str, str]]


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


def article_text(report: Report, *, verify_ssl: bool) -> str:
    html_text = request_text(report.url, verify_ssl=verify_ssl)
    match = re.search(
        r'<div[^>]*class="[^"]*article[^"]*"[^>]*>(.*?)<div class="article-file"',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return repair_mojibake(strip_tags(match.group(1) if match else html_text))


def search_value(patterns: list[str], text: str, default: str = "-") -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return default


def extract_report_summary(report: Report, text: str) -> ReportSummary:
    week = search_value([r"(\d+)\s*주차", r"(\d+)\s*주"], report.title, "-")

    influenza = search_value(
        [
            r"인플루엔자 의사환자[^.。]*?수는\s*(\d+(?:\.\d+)?)\s*명",
            r"1,000명당 인플루엔자[^.。]*?수는\s*(\d+(?:\.\d+)?)\s*명",
        ],
        text,
    )

    influenza_direction = "증가" if re.search(r"인플루엔자[^.。]*전주[^.。]*증가", text) else "감소"

    ari_cases_raw = search_value(
        [
            r"급성호흡기감염증[^.。]*?(\d{1,3}(?:,\d{3})*|\d+)\s*명",
            r"기타호흡기감염증[^.。]*?(\d{1,3}(?:,\d{3})*|\d+)\s*건",
        ],
        text,
    )
    ari_previous = search_value(
        [
            r"급성호흡기감염증[^.。]*?전주\((\d{1,3}(?:,\d{3})*|\d+)\s*명\)",
            r"기타호흡기감염증[^.。]*?전주\((\d{1,3}(?:,\d{3})*|\d+)\s*건\)",
        ],
        text,
    )
    ari_delta = "-"
    if ari_cases_raw != "-" and ari_previous != "-":
        current = int(ari_cases_raw.replace(",", ""))
        previous = int(ari_previous.replace(",", ""))
        diff = current - previous
        if diff > 0:
            ari_delta = f"{diff:,}명 증가"
        elif diff < 0:
            ari_delta = f"{abs(diff):,}명 감소"
        else:
            ari_delta = "변동 없음"

    ari_section_match = re.search(r"3\.\s*급성호흡기감염증(.*?)(?:4\.\s*중증급성호흡기감염증|$)", text)
    ari_section = ari_section_match.group(1) if ari_section_match else text
    virus_aliases = [
        ("리노바이러스", "리노"),
        ("사람 메타뉴모바이러스", "메타뉴모"),
        ("파라인플루엔자바이러스", "파라인플루"),
        ("파라인플루엔자 바이러스", "파라인플루"),
        ("사람코로나바이러스", "코로나"),
        ("아데노바이러스", "아데노"),
        ("호흡기세포융합바이러스", "RSV"),
    ]
    key_viruses: list[tuple[str, str]] = []
    seen_labels: set[str] = set()
    for full_name, label in virus_aliases:
        value = search_value([rf"{full_name}\s*(\d+(?:\.\d+)?)\s*%"], ari_section)
        if value != "-" and label not in seen_labels:
            key_viruses.append((label, f"{value}%"))
            seen_labels.add(label)
    key_viruses = key_viruses[:5]

    return ReportSummary(
        week=week,
        influenza=f"{influenza}‰" if influenza != "-" else "-",
        influenza_direction=influenza_direction,
        ari_cases=f"{ari_cases_raw}명" if ari_cases_raw != "-" else "-",
        ari_delta=ari_delta,
        key_viruses=key_viruses,
    )


def find_font(size: int, *, bold: bool = False) -> Any:
    from PIL import ImageFont

    candidates = [
        r"C:\Windows\Fonts\malgunbd.ttf" if bold else r"C:\Windows\Fonts\malgun.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def draw_card(draw: Any, box: tuple[int, int, int, int], *, radius: int, fill: str, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline)


def render_summary_image(report: Report, summary: ReportSummary, output_path: Path) -> None:
    from PIL import Image, ImageDraw

    width, height = 1080, 1500
    image = Image.new("RGB", (width, height), "#f4f1ff")
    draw = ImageDraw.Draw(image)

    title_font = find_font(54, bold=True)
    subtitle_font = find_font(25)
    label_font = find_font(26, bold=True)
    value_font = find_font(58, bold=True)
    small_font = find_font(23)
    section_font = find_font(38, bold=True)
    item_font = find_font(31, bold=True)

    for y in range(height):
        ratio = y / height
        red = int(94 + 34 * ratio)
        green = int(100 + 18 * ratio)
        blue = int(232 - 28 * ratio)
        draw.line([(0, y), (width, y)], fill=(red, green, blue))

    draw.text((80, 82), "호흡기 감염병 모니터링", font=title_font, fill="#ffffff")
    draw.text((84, 154), f"{report.published_date} · {summary.week}주차 리포트", font=subtitle_font, fill="#e7e5ff")

    cards = [
        ((70, 245, 500, 465), "현재 주차", f"{summary.week}주차", "#dff7ff", "#0891b2"),
        ((580, 245, 1010, 465), "인플루엔자", summary.influenza, "#fff1f2", "#e11d48"),
        ((70, 505, 500, 725), "기타호흡기감염증", summary.ari_cases, "#ecfdf5", "#16a34a"),
        ((580, 505, 1010, 725), "전주 대비", summary.ari_delta, "#fffbeb", "#d97706"),
    ]
    for box, label, value, chip_fill, accent in cards:
        draw_card(draw, box, radius=34, fill="#ffffff")
        x1, y1, x2, _ = box
        draw.rounded_rectangle((x1 + 28, y1 + 30, x1 + 178, y1 + 78), radius=18, fill=chip_fill)
        draw.text((x1 + 48, y1 + 39), label[:8], font=small_font, fill=accent)
        draw.text((x1 + 36, y1 + 108), value, font=value_font, fill="#111827")
        if label == "인플루엔자":
            draw.text((x1 + 38, y1 + 178), f"전주 대비 {summary.influenza_direction}", font=subtitle_font, fill="#6b7280")
        else:
            draw.text((x1 + 38, y1 + 178), label, font=subtitle_font, fill="#6b7280")

    draw_card(draw, (70, 800, 1010, 1235), radius=36, fill="#ffffff")
    draw.text((110, 850), "주요 바이러스 분포", font=section_font, fill="#111827")
    colors = ["#2563eb", "#ef4444", "#f59e0b", "#8b5cf6", "#10b981"]
    max_value = 1
    parsed: list[tuple[str, int, str]] = []
    for name, value in summary.key_viruses:
        number = int(re.sub(r"\D", "", value) or "0")
        parsed.append((name, number, value))
        max_value = max(max_value, number)
    parsed.sort(key=lambda item: item[1], reverse=True)
    for index, (name, number, value) in enumerate(parsed):
        y = 928 + index * 62
        color = colors[index % len(colors)]
        draw.text((115, y - 2), name, font=item_font, fill="#111827")
        bar_left = 330
        bar_width = int(400 * number / max_value)
        draw.rounded_rectangle((bar_left, y + 10, bar_left + bar_width, y + 40), radius=15, fill=color)
        draw.text((820, y - 2), value, font=item_font, fill="#111827")

    draw_card(draw, (70, 1280, 1010, 1410), radius=30, fill="#111827")
    draw.text((110, 1316), "질병관리청 감염병포털 최신 주간소식지 기준", font=subtitle_font, fill="#ffffff")
    draw.text((110, 1360), "원문은 카카오톡 메시지의 링크에서 확인하세요.", font=small_font, fill="#c7d2fe")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=True)


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


def send_kakao_message(access_token: str, report: Report, summary: ReportSummary, config: dict[str, Any], *, verify_ssl: bool) -> None:
    image_url = config.get("report_image_url") or os.environ.get("REPORT_IMAGE_URL")
    description = (
        f"인플루엔자 {summary.influenza} · 기타호흡기 {summary.ari_cases} "
        f"· 주요 바이러스 {', '.join(f'{name} {value}' for name, value in summary.key_viruses[:3])}"
    )
    template_object = {
        "object_type": "feed",
        "content": {
            "title": f"감염병 주간 리포트 {summary.week}주차",
            "description": description[:180],
            "link": {
                "web_url": report.url,
                "mobile_web_url": report.url,
            },
        },
        "item_content": {
            "profile_text": "KDCA Monitor",
            "items": [
                {"item": "인플루엔자", "item_op": summary.influenza},
                {"item": "기타호흡기", "item_op": summary.ari_cases},
                {"item": "전주 대비", "item_op": summary.ari_delta},
                *[
                    {"item": name, "item_op": value}
                    for name, value in summary.key_viruses[:2]
                ],
            ],
            "sum": "원문",
            "sum_op": "확인",
        },
    }
    if image_url:
        template_object["content"]["image_url"] = image_url
        template_object["content"]["image_width"] = 1080
        template_object["content"]["image_height"] = 1500

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
    summary = extract_report_summary(latest_report, article_text(latest_report, verify_ssl=verify_ssl))
    image_path = Path(config.get("report_image_path", BASE_DIR / "latest_report.png"))
    render_summary_image(latest_report, summary, image_path)

    print(f"Latest report: {latest_report.title} ({latest_report.published_date})")
    print(latest_report.url)
    print(f"Summary image: {image_path}")

    already_sent = not disable_state and state.get("last_sent_doc_no") == latest_report.doc_no
    if already_sent and not force:
        print("No new report. Skipping KakaoTalk message.")
        return 0

    if dry_run:
        print("Dry run only. KakaoTalk message was not sent.")
        return 0

    access_token = refresh_kakao_token(config, config_path)
    send_kakao_message(access_token, latest_report, summary, config, verify_ssl=verify_ssl)

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
