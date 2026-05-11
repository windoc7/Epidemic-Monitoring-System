#!/usr/bin/env python
"""Railway web service for the Choice ENT respiratory infection report."""

from __future__ import annotations

import html
import math
import os
import re
from pathlib import Path

from flask import Flask, Response

from kdca_kakao_report import (
    KDCA_LIST_URL,
    Report,
    ReportSummary,
    article_text,
    extract_report_summary,
    find_latest_report,
    render_summary_image,
    request_text,
)

BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "latest_report.png"
STATE_PATH = BASE_DIR / "state.json"
_cache: dict = {}
app = Flask(__name__)


def _load_history(key: str) -> list[tuple[str, float]]:
    try:
        import json
        with STATE_PATH.open(encoding="utf-8") as f:
            state = json.load(f)
        history = state.get("weekly_history", {})
        if not history:
            return []
        weeks = sorted(history.keys(), key=lambda w: int(w) if w.isdigit() else 0)
        return [(f"{w}주", history[w][key]) for w in weeks if history[w].get(key)]
    except Exception:
        return []


def load_ari_history() -> list[tuple[str, float]]:
    return _load_history("ari")


def load_enteric_history() -> list[tuple[str, float]]:
    return _load_history("enteric")

VIRUS_COLORS = ["#3b82f6", "#14b8a6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#6b7280"]


def verify_ssl() -> bool:
    return os.environ.get("VERIFY_SSL", "").strip().lower() in {"1", "true", "yes", "on"}


def load_report() -> tuple[object, object]:
    try:
        ssl = verify_ssl()
        report = find_latest_report(request_text(KDCA_LIST_URL, verify_ssl=ssl))
        if _cache.get("doc_no") != report.doc_no:
            summary = extract_report_summary(report, article_text(report, verify_ssl=ssl))
            render_summary_image(report, summary, IMAGE_PATH)
            _cache["doc_no"] = report.doc_no
            _cache["report"] = report
            _cache["summary"] = summary
        return _cache["report"], _cache["summary"]
    except Exception as exc:
        print(f"KDCA fetch failed, using cached state: {exc}", flush=True)
        if _cache.get("report") and _cache.get("summary"):
            return _cache["report"], _cache["summary"]
        return load_cached_report()


def load_cached_report() -> tuple[Report, ReportSummary]:
    import json

    with STATE_PATH.open(encoding="utf-8") as f:
        state = json.load(f)

    history = state.get("weekly_history", {})
    weeks = sorted((w for w in history if w.isdigit()), key=int)
    latest_week = weeks[-1] if weeks else "?"
    latest = history.get(latest_week, {})
    previous = history.get(weeks[-2], {}) if len(weeks) > 1 else {}

    def trend(key: str) -> list[tuple[str, float]]:
        return [(f"{week}주", float(history[week].get(key, 0))) for week in weeks if key in history[week]]

    influenza_value = float(latest.get("influenza", 0))
    previous_flu = float(previous.get("influenza", influenza_value))
    direction = "증가" if influenza_value > previous_flu else "감소" if influenza_value < previous_flu else "변동 없음"

    report = Report(
        doc_no=str(state.get("last_sent_doc_no", "cached")),
        title=str(state.get("last_sent_title", "감염병 표본감시 주간소식지")),
        department="질병관리청",
        published_date=str(state.get("last_sent_at", "")).split("T")[0],
        url=str(state.get("last_sent_url", KDCA_LIST_URL)),
    )
    summary = ReportSummary(
        week=latest_week,
        influenza=f"{influenza_value:g}‰",
        influenza_direction=direction,
        influenza_trend=trend("influenza"),
        ari_cases=f"{int(float(latest.get('ari', 0))):,}명",
        ari_delta="KDCA 실시간 연결 실패 - 저장된 수치 표시",
        key_viruses=[],
        ari_trend=trend("ari"),
        epidemic_threshold=8.6,
        corona_cases=f"{int(float(latest.get('corona', 0))):,}명",
        corona_delta="저장된 수치",
        corona_trend=trend("corona"),
        enteric_cases=f"{int(float(latest.get('enteric', 0))):,}명",
        enteric_delta="저장된 수치",
        enteric_viruses=[],
    )
    _cache["doc_no"] = report.doc_no
    _cache["report"] = report
    _cache["summary"] = summary
    return report, summary


def num(value: str) -> float:
    return float(re.sub(r"[^0-9.]", "", value) or "0")


def line_chart_svg(trend: list, color: str, grad_id: str) -> str:
    if not trend:
        return '<text x="150" y="60" text-anchor="middle" fill="#94a3b8" font-size="13">데이터 없음</text>'
    values = [v for _, v in trend]
    weeks = [w for w, _ in trend]
    lo, hi = min(values), max(values)
    span = max(hi - lo, 0.5)
    W, H, pl, pr, pt, pb = 340, 100, 42, 10, 8, 22
    cw = W - pl - pr
    n = len(values)
    step = cw / max(n - 1, 1)

    pts = [(pl + i * step, pt + (1 - (v - lo) / span) * H) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = line + f" {pts[-1][0]:.1f},{pt+H} {pts[0][0]:.1f},{pt+H}"

    grid = "".join(
        f'<line x1="{pl}" y1="{pt + (1-(v-lo)/span)*H:.1f}" x2="{W-pr}" y2="{pt + (1-(v-lo)/span)*H:.1f}" stroke="#f1f5f9" stroke-width="1"/>'
        f'<text x="{pl-4}" y="{pt + (1-(v-lo)/span)*H:.1f}" text-anchor="end" dominant-baseline="middle" fill="#94a3b8" font-size="9">{v:.0f}</text>'
        for v in [lo, (lo+hi)/2, hi]
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}" stroke="white" stroke-width="2"/>'
        for x, y in pts
    )
    xlabels = "".join(
        f'<text x="{x:.1f}" y="{pt+H+pb-2}" text-anchor="middle" fill="#94a3b8" font-size="9">{html.escape(w)}</text>'
        for (x, _), w in zip(pts, weeks)
    )
    last_x, last_y = pts[-1]
    last_label = f"{values[-1]:.1f}" if values[-1] < 100 else f"{int(values[-1]):,}"
    tag_x = min(last_x, W - pr - 22)
    tag = (f'<rect x="{tag_x-20:.1f}" y="{last_y-22:.1f}" width="42" height="16" rx="8" fill="{color}"/>'
           f'<text x="{tag_x+1:.1f}" y="{last_y-11:.1f}" text-anchor="middle" fill="white" font-size="9" font-weight="700">{last_label}</text>')

    return f"""<svg viewBox="0 0 {W} {pt+H+pb}" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="{color}" stop-opacity=".2"/><stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>
  {grid}
  <polygon points="{area}" fill="url(#{grad_id})"/>
  <polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  {dots}{tag}{xlabels}
</svg>"""


def donut_svg(viruses: list) -> tuple[str, str]:
    if not viruses:
        return '<text x="80" y="84" text-anchor="middle" fill="#94a3b8" font-size="11">데이터 없음</text>', ""
    total = sum(num(v) for _, v in viruses) or 1
    cx, cy, ro, ri = 80, 80, 70, 42
    paths, legend = [], []
    angle = -90.0
    for i, (name, val) in enumerate(viruses[:6]):
        pct = num(val) / total
        sweep = pct * 360
        if sweep < 0.5:
            continue
        color = VIRUS_COLORS[i % len(VIRUS_COLORS)]
        end = angle + sweep
        large = 1 if sweep > 180 else 0
        def pt(r: float, a: float) -> str:
            rad = math.radians(a)
            return f"{cx + r*math.cos(rad):.2f},{cy + r*math.sin(rad):.2f}"
        d = f"M{pt(ro,angle)} A{ro},{ro},0,{large},1,{pt(ro,end)} L{pt(ri,end)} A{ri},{ri},0,{large},0,{pt(ri,angle)}Z"
        paths.append(f'<path d="{d}" fill="{color}" stroke="white" stroke-width="2"/>')
        legend.append(
            f'<div class="leg-row"><span class="leg-dot" style="background:{color}"></span>'
            f'<span class="leg-name">{html.escape(name)}</span>'
            f'<span class="leg-val">{html.escape(val)}</span></div>'
        )
        angle = end
    return "\n".join(paths), "\n".join(legend)


def render_html() -> str:
    report, summary = load_report()
    flu_svg = line_chart_svg(summary.influenza_trend, "#fb923c", "ag")
    ari_history = load_ari_history()
    ari_svg = line_chart_svg(ari_history or summary.ari_trend, "#a78bfa", "bg")
    enteric_history = load_enteric_history()
    enteric_trend_svg = line_chart_svg(enteric_history, "#34d399", "eg") if enteric_history else ""
    corona_svg = line_chart_svg(summary.corona_trend, "#22d3ee", "cg")
    donut_paths, legend_html = donut_svg(summary.key_viruses)
    enteric_donut, enteric_legend = donut_svg(summary.enteric_viruses)
    top_virus = summary.key_viruses[0] if summary.key_viruses else ("—", "—")
    direction_icon = "▲" if summary.influenza_direction == "증가" else "▼"
    direction_color = "#fb923c" if summary.influenza_direction == "증가" else "#34d399"
    flu_val = num(summary.influenza.replace("‰", ""))
    is_epidemic = flu_val >= summary.epidemic_threshold
    epidemic_label = "유행중" if is_epidemic else "유행 아님"
    epidemic_color = "#ef4444" if is_epidemic else "#10b981"
    epidemic_bg = "rgba(239,68,68,.2)" if is_epidemic else "rgba(16,185,129,.15)"

    flu5_svg = line_chart_svg(summary.influenza_trend[-5:], "#fb923c", "fg")

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta property="og:title" content="호흡기 감염병 모니터링">
  <meta property="og:image" content="/latest_report.png">
  <title>호흡기 감염병 모니터링</title>
  <style>
    @font-face{{font-family:"LaundryGothic";src:url("/fonts/laundry-bold.woff") format("woff");font-weight:700;font-style:normal}}
    @font-face{{font-family:"LaundryGothic";src:url("/fonts/laundry-regular.woff") format("woff");font-weight:400;font-style:normal}}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;background:#0d1117;height:100vh;overflow:hidden;color:#fff}}
    .wrap{{max-width:1400px;margin:0 auto;padding:14px 24px 10px;height:100vh;display:flex;flex-direction:column;gap:10px}}

    /* header */
    .hdr{{display:flex;align-items:center;gap:16px;flex-shrink:0}}
    .hdr-week{{font-size:22px;font-weight:900;color:#60a5fa;background:rgba(59,130,246,.15);padding:4px 14px;border-radius:10px;white-space:nowrap}}
    .hdr-title{{font-family:"LaundryGothic",sans-serif;font-size:28px;font-weight:700;letter-spacing:3px;background:linear-gradient(90deg,#e2e8f0 0%,#ffffff 40%,#94a3b8 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;flex:1}}
    .hdr-right{{display:flex;align-items:center;gap:8px}}
    .hdr-logo{{width:36px;height:36px;object-fit:contain;border-radius:8px;background:rgba(255,255,255,.05);padding:3px}}
    .hdr-info{{text-align:right;color:#475569;font-size:11px;line-height:1.6}}
    .hdr-info strong{{color:#64748b;font-size:12px;font-weight:700;display:block}}

    /* main grid */
    .main{{display:grid;grid-template-columns:1fr 1fr 1fr;grid-template-rows:1fr 1fr;gap:10px;flex:1;min-height:0}}

    /* section card */
    .sec{{border-radius:16px;overflow:hidden;display:flex;flex-direction:column;min-height:0}}
    .sec-head{{padding:12px 16px 8px;display:flex;align-items:center;gap:10px;flex-shrink:0}}
    .sec-icon{{font-size:20px}}
    .sec-name{{font-size:11px;font-weight:700;letter-spacing:.5px;opacity:.8;text-transform:uppercase}}
    .sec-body{{padding:0 16px 12px;flex:1;display:flex;flex-direction:column;min-height:0}}
    .sec-val{{font-size:clamp(22px,2.5vw,34px);font-weight:900;line-height:1;margin-bottom:4px}}
    .sec-sub{{font-size:11px;opacity:.7;font-weight:600;margin-bottom:6px}}
    .sec-chart{{flex:1;min-height:0;overflow:hidden}}
    .sec-chart svg{{width:100%;height:100%;display:block}}

    .s-flu{{background:linear-gradient(150deg,#7c2d12,#c2410c,#ea580c)}}
    .s-corona{{background:linear-gradient(150deg,#164e63,#0e7490,#06b6d4)}}
    .s-enteric{{background:linear-gradient(150deg,#064e3b,#047857,#10b981)}}
    .s-virus{{background:#161b22;border:1px solid rgba(255,255,255,.07)}}

    /* bottom row spans */
    .span3{{grid-column:1 / -1}}

    /* donut+trend panel */
    .virus-panel{{display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:center;height:100%;padding:12px 16px}}
    .virus-title{{font-size:12px;font-weight:700;color:#64748b;margin-bottom:10px}}
    .donut-area{{display:flex;align-items:center;gap:14px}}
    .donut-area svg{{width:130px;height:130px;flex-shrink:0}}
    .leg-row{{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:12px}}
    .leg-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
    .leg-name{{flex:1;font-weight:600;color:#e2e8f0}}
    .leg-val{{color:#64748b;font-size:11px;font-weight:700}}

    /* footer */
    .footer{{flex-shrink:0;display:flex;justify-content:space-between;align-items:center;padding:6px 4px;border-top:1px solid rgba(255,255,255,.05)}}
    .footer-src{{font-size:11px;color:#334155}}
    .footer-src a{{color:#475569;font-weight:700;text-decoration:none}}
    .footer-players{{font-size:15px;font-weight:900;background:linear-gradient(90deg,#f97316,#f59e0b,#84cc16,#22d3ee,#818cf8,#e879f9);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
  </style>
</head>
<body>
<div class="wrap">

  <div class="hdr">
    <div class="hdr-week">📅 {html.escape(summary.week)}주차</div>
    <div class="hdr-title">호흡기 감염병 모니터링</div>
    <div class="hdr-right">
      <img class="hdr-logo" src="/logo.png" alt="CI">
      <div class="hdr-info">
        <strong>초이스 이비인후과 제공</strong>
        {html.escape(report.published_date)} 기준
      </div>
    </div>
  </div>

  <div class="main">

    <!-- 인플루엔자 -->
    <div class="sec s-flu">
      <div class="sec-head"><span class="sec-icon">🌡</span><span class="sec-name">인플루엔자 의사환자분율</span></div>
      <div class="sec-body">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:3px">
          <div class="sec-val" style="margin:0">{html.escape(summary.influenza)}</div>
          <div style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:800;background:{epidemic_bg};color:{epidemic_color};border:1px solid {epidemic_color}">{epidemic_label}</div>
        </div>
        <div class="sec-sub" style="color:{direction_color}">{direction_icon} {html.escape(summary.influenza_direction)} · 기준 {summary.epidemic_threshold}‰</div>
        <div class="sec-chart">{flu_svg}</div>
      </div>
    </div>

    <!-- 코로나19 -->
    <div class="sec s-corona">
      <div class="sec-head"><span class="sec-icon">🦠</span><span class="sec-name">코로나19 입원환자</span></div>
      <div class="sec-body">
        <div class="sec-val">{html.escape(summary.corona_cases)}</div>
        <div class="sec-sub">{html.escape(summary.corona_delta)}</div>
        <div class="sec-chart">{corona_svg}</div>
      </div>
    </div>

    <!-- 장관감염증 -->
    <div class="sec s-enteric">
      <div class="sec-head"><span class="sec-icon">🧫</span><span class="sec-name">장관감염증</span></div>
      <div class="sec-body">
        <div class="sec-val" style="font-size:clamp(20px,2vw,30px)">{html.escape(summary.enteric_cases)}</div>
        <div class="sec-sub">{html.escape(summary.enteric_delta)}</div>
        <div class="sec-chart">
          {enteric_trend_svg if enteric_trend_svg else "<div style='opacity:.45;font-size:11px;padding-top:6px'>데이터 누적 중 — 매주 자동 갱신</div>"}
        </div>
      </div>
    </div>

    <!-- 바이러스 분포 + 기타호흡기감염증 5주 추이 (하단 전체) -->
    <div class="sec s-virus span3">
      <div style="display:grid;grid-template-columns:1fr 1fr;flex:1;min-height:0;padding:0 16px 10px;align-items:center;gap:20px">
        <div style="display:flex;flex-direction:column;align-items:center">
          <div style="font-size:11px;font-weight:700;color:#64748b;align-self:flex-start;margin-bottom:8px">🔬 주요 바이러스 분포</div>
          <div style="display:flex;align-items:center;gap:18px">
            <svg viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg" style="width:260px;height:260px;flex-shrink:0">
              {donut_paths}
              <circle cx="80" cy="80" r="38" fill="#0d1117"/>
              <text x="80" y="75" text-anchor="middle" fill="#f1f5f9" font-size="11" font-weight="800">{html.escape(top_virus[0])}</text>
              <text x="80" y="90" text-anchor="middle" fill="#94a3b8" font-size="9">{html.escape(top_virus[1])}</text>
            </svg>
            <div style="font-size:12px;line-height:1.9">{legend_html}</div>
          </div>
        </div>
        <div style="padding-left:16px;border-left:1px solid rgba(255,255,255,.06);display:flex;flex-direction:column">
          <div style="font-size:11px;font-weight:700;color:#64748b;margin-bottom:8px">📊 기타호흡기감염증 최근 5주 추이</div>
          <div style="flex:1">{ari_svg}</div>
        </div>
      </div>
    </div>


  </div>

  <div class="footer">
    <div class="footer-src">질병관리청 감염병포털 기반 자동 요약 &nbsp;·&nbsp;<a href="{html.escape(report.url)}" target="_blank" rel="noreferrer">원문 보기 →</a></div>
    <div class="footer-players">The players forever!!!</div>
  </div>
</div>
</body>
</html>"""


def send_bytes(body: bytes, content_type: str, status: int = 200) -> Response:
    return Response(body, status=status, content_type=content_type, headers={"Cache-Control": "no-store"})


@app.get("/health")
def health() -> Response:
    return send_bytes(b"ok\n", "text/plain; charset=utf-8")


@app.get("/logo.png")
def logo() -> Response:
    return send_bytes((BASE_DIR / "choice_ent_logo.png").read_bytes(), "image/png")


@app.get("/fonts/laundry-bold.woff")
def laundry_bold() -> Response:
    font_path = BASE_DIR / "LaundryGothic_TTF" / "webfont" / "런드리고딕 Bold.woff"
    return send_bytes(font_path.read_bytes(), "font/woff")


@app.get("/fonts/laundry-regular.woff")
def laundry_regular() -> Response:
    font_path = BASE_DIR / "LaundryGothic_TTF" / "webfont" / "런드리고딕 Regular.woff"
    return send_bytes(font_path.read_bytes(), "font/woff")


@app.get("/latest_report.png")
def latest_report_image() -> Response:
    try:
        load_report()
        return send_bytes(IMAGE_PATH.read_bytes(), "image/png")
    except Exception as exc:
        if IMAGE_PATH.exists():
            print(f"image refresh failed, serving cached image: {exc}", flush=True)
            return send_bytes(IMAGE_PATH.read_bytes(), "image/png")
        print(f"image error: {exc}", flush=True)
        return send_bytes(f"image error: {exc}\n".encode("utf-8"), "text/plain; charset=utf-8", status=503)


@app.get("/")
def index() -> Response:
    try:
        return send_bytes(render_html().encode("utf-8"), "text/html; charset=utf-8")
    except Exception as exc:
        print(f"render error: {exc}", flush=True)
        return send_bytes(f"<pre>오류: {exc}</pre>".encode("utf-8"), "text/html; charset=utf-8", status=500)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    print(f"Starting Flask development server on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
