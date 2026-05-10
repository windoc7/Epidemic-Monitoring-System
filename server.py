#!/usr/bin/env python
"""Railway web service for the Choice ENT respiratory infection report."""

from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kdca_kakao_report import (
    KDCA_LIST_URL,
    article_text,
    extract_report_summary,
    find_latest_report,
    render_summary_image,
    request_text,
)


BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "latest_report.png"

_cache: dict = {}


def verify_ssl() -> bool:
    return os.environ.get("VERIFY_SSL", "").strip().lower() in {"1", "true", "yes", "on"}


def load_report() -> tuple[object, object]:
    ssl = verify_ssl()
    report = find_latest_report(request_text(KDCA_LIST_URL, verify_ssl=ssl))
    if _cache.get("doc_no") != report.doc_no:
        summary = extract_report_summary(report, article_text(report, verify_ssl=ssl))
        render_summary_image(report, summary, IMAGE_PATH)
        _cache["doc_no"] = report.doc_no
        _cache["report"] = report
        _cache["summary"] = summary
    return _cache["report"], _cache["summary"]


def number_from(value: str) -> float:
    import re

    return float(re.sub(r"[^0-9.]", "", value) or "0")


def render_html() -> str:
    report, summary = load_report()
    trend = summary.influenza_trend
    virus_items = summary.key_viruses[:4]
    max_virus = max([number_from(value) for _, value in virus_items] or [1])
    trend_values = [value for _, value in trend] or [0]
    min_trend, max_trend = min(trend_values), max(trend_values)
    trend_span = max(max_trend - min_trend, 1)

    points = []
    for index, (week, value) in enumerate(trend):
        x = 8 + index * (84 / max(len(trend) - 1, 1))
        y = 78 - ((value - min_trend) / trend_span) * 58
        points.append(f"{x:.1f},{y:.1f}")

    virus_html = "\n".join(
        f"""
        <div class="virus-row">
          <div class="virus-name">{html.escape(name)}</div>
          <div class="virus-track"><span style="width:{number_from(value) / max_virus * 100:.1f}%"></span></div>
          <div class="virus-value">{html.escape(value)}</div>
        </div>
        """
        for name, value in virus_items
    )
    trend_labels = "\n".join(f"<span>{html.escape(week)}</span>" for week, _ in trend)

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta property="og:title" content="초이스 이비인후과 호흡기 감염병 리포트">
  <meta property="og:description" content="{summary.week}주차 자동 요약 · 인플루엔자 {summary.influenza} · 기타호흡기 {summary.ari_cases}">
  <meta property="og:image" content="/latest_report.png">
  <title>초이스 이비인후과 호흡기 감염병 리포트</title>
  <style>
    :root {{
      color-scheme: light;
      --navy:#08111f;
      --navy2:#0f172a;
      --ink:#111827;
      --muted:#64748b;
      --line:#dbe3ef;
      --cyan:#22d3ee;
      --blue:#2563eb;
      --green:#10b981;
      --red:#f43f5e;
      --orange:#f59e0b;
      --purple:#8b5cf6;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      min-height:100vh;
      font-family:"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;
      background:
        radial-gradient(circle at 85% 0%, rgba(20,184,166,.28), transparent 28rem),
        radial-gradient(circle at 0% 78%, rgba(37,99,235,.22), transparent 26rem),
        linear-gradient(145deg, #07111f 0%, #11233e 55%, #07111f 100%);
      color:var(--ink);
    }}
    main {{
      width:min(1120px, calc(100% - 32px));
      margin:0 auto;
      padding:44px 0 56px;
    }}
    .shell {{
      background:#f8fafc;
      border-radius:38px;
      overflow:hidden;
      box-shadow:0 28px 90px rgba(0,0,0,.34);
      border:1px solid rgba(255,255,255,.22);
    }}
    .hero {{
      position:relative;
      display:grid;
      grid-template-columns:128px 1fr auto;
      gap:28px;
      align-items:center;
      padding:42px;
      background:linear-gradient(135deg, #0f172a 0%, #111b31 56%, #0a2a42 100%);
      color:white;
    }}
    .logo {{
      width:112px;
      height:112px;
      object-fit:contain;
      filter:drop-shadow(0 12px 18px rgba(0,0,0,.24));
    }}
    .eyebrow {{
      color:var(--cyan);
      font-size:20px;
      font-weight:800;
      letter-spacing:.08em;
    }}
    h1 {{
      margin:8px 0 10px;
      font-size:64px;
      line-height:1.05;
      letter-spacing:0;
    }}
    .sub {{
      color:#cbd5e1;
      font-size:24px;
    }}
    .badge {{
      align-self:start;
      padding:16px 24px;
      border-radius:999px;
      background:#ecfeff;
      color:#0e7490;
      font-weight:900;
      font-size:20px;
    }}
    .content {{ padding:34px 42px 42px; }}
    .metrics {{
      display:grid;
      grid-template-columns:repeat(4, 1fr);
      gap:22px;
    }}
    .card {{
      background:white;
      border:1px solid var(--line);
      border-radius:24px;
      padding:26px;
      min-height:190px;
      box-shadow:0 12px 36px rgba(15,23,42,.06);
    }}
    .pill {{
      display:inline-flex;
      padding:8px 18px;
      border-radius:999px;
      color:white;
      font-weight:900;
      font-size:18px;
    }}
    .value {{
      margin-top:28px;
      font-size:54px;
      line-height:1;
      font-weight:900;
      color:var(--navy2);
    }}
    .note {{
      margin-top:8px;
      color:var(--muted);
      font-size:21px;
    }}
    .grid {{
      display:grid;
      grid-template-columns:1.1fr .9fr;
      gap:24px;
      margin-top:24px;
    }}
    .panel {{
      border-radius:28px;
      padding:32px;
      background:var(--navy2);
      color:white;
      min-height:330px;
    }}
    .panel.light {{
      background:white;
      color:var(--ink);
      border:1px solid var(--line);
    }}
    .panel-title {{
      display:flex;
      justify-content:space-between;
      align-items:baseline;
      gap:20px;
      font-size:34px;
      font-weight:900;
      margin-bottom:22px;
    }}
    .panel-title strong {{
      color:#67e8f9;
      font-size:58px;
    }}
    .chart {{
      width:100%;
      height:180px;
      overflow:visible;
    }}
    .axis {{
      display:flex;
      justify-content:space-between;
      color:#94a3b8;
      font-size:19px;
      margin:0 8px;
    }}
    .virus-row {{
      display:grid;
      grid-template-columns:120px 1fr 72px;
      align-items:center;
      gap:18px;
      margin:20px 0;
      font-size:22px;
      font-weight:800;
    }}
    .virus-track {{
      height:22px;
      background:#e2e8f0;
      border-radius:999px;
      overflow:hidden;
    }}
    .virus-track span {{
      display:block;
      height:100%;
      border-radius:999px;
      background:linear-gradient(90deg, var(--blue), var(--cyan));
    }}
    .source {{
      display:flex;
      justify-content:space-between;
      align-items:center;
      gap:18px;
      margin-top:24px;
      padding:22px 26px;
      border-radius:22px;
      background:#e8eef6;
      color:#334155;
      font-size:18px;
    }}
    .source a {{
      color:#0f766e;
      font-weight:900;
      text-decoration:none;
    }}
    @media (max-width: 860px) {{
      main {{ width:100%; padding:0; }}
      .shell {{ border-radius:0; min-height:100vh; }}
      .hero {{ grid-template-columns:74px 1fr; padding:28px 22px; gap:18px; }}
      .logo {{ width:70px; height:70px; }}
      .badge {{ grid-column:1 / -1; justify-self:start; font-size:15px; padding:10px 16px; }}
      h1 {{ font-size:38px; }}
      .sub {{ font-size:17px; }}
      .content {{ padding:22px; }}
      .metrics {{ grid-template-columns:repeat(2, 1fr); gap:14px; }}
      .card {{ padding:18px; min-height:150px; border-radius:20px; }}
      .value {{ font-size:36px; }}
      .note {{ font-size:15px; }}
      .grid {{ grid-template-columns:1fr; }}
      .panel-title {{ font-size:25px; }}
      .panel-title strong {{ font-size:42px; }}
      .virus-row {{ grid-template-columns:90px 1fr 64px; font-size:18px; gap:12px; }}
      .source {{ align-items:flex-start; flex-direction:column; font-size:15px; }}
    }}
  </style>
</head>
<body>
<main>
  <section class="shell">
    <header class="hero">
      <img class="logo" src="/logo.png" alt="초이스 이비인후과 로고">
      <div>
        <div class="eyebrow">CHOICE ENT CLINIC</div>
        <h1>초이스 이비인후과</h1>
        <div class="sub">호흡기 감염병 모니터링 · {html.escape(report.published_date)} · {html.escape(summary.week)}주차</div>
      </div>
      <div class="badge">KDCA DATA</div>
    </header>
    <div class="content">
      <section class="metrics">
        <article class="card">
          <span class="pill" style="background:var(--blue)">WEEK</span>
          <div class="value">{html.escape(summary.week)}주차</div>
          <div class="note">현재 보고 주차</div>
        </article>
        <article class="card">
          <span class="pill" style="background:var(--red)">ILI</span>
          <div class="value">{html.escape(summary.influenza)}</div>
          <div class="note">전주 대비 {html.escape(summary.influenza_direction)}</div>
        </article>
        <article class="card">
          <span class="pill" style="background:var(--green)">ARI</span>
          <div class="value">{html.escape(summary.ari_cases)}</div>
          <div class="note">급성호흡기 입원환자</div>
        </article>
        <article class="card">
          <span class="pill" style="background:var(--orange)">DELTA</span>
          <div class="value">{html.escape(summary.ari_delta)}</div>
          <div class="note">전주 대비</div>
        </article>
      </section>

      <section class="grid">
        <article class="panel">
          <div class="panel-title"><span>인플루엔자 의사환자분율 추이</span><strong>{html.escape(summary.influenza)}</strong></div>
          <svg class="chart" viewBox="0 0 100 100" preserveAspectRatio="none">
            <line x1="8" y1="82" x2="92" y2="82" stroke="#334155" stroke-width="1" />
            <polyline points="{' '.join(points)}" fill="none" stroke="#38bdf8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
            {''.join(f'<circle cx="{point.split(",")[0]}" cy="{point.split(",")[1]}" r="2.4" fill="#ffffff" stroke="#38bdf8" stroke-width="1.6"/>' for point in points)}
          </svg>
          <div class="axis">{trend_labels}</div>
        </article>
        <article class="panel light">
          <div class="panel-title"><span>주요 바이러스 분포</span></div>
          {virus_html}
        </article>
      </section>

      <div class="source">
        <span>질병관리청 감염병포털 최신 주간소식지 기반 자동 요약</span>
        <a href="{html.escape(report.url)}" target="_blank" rel="noreferrer">원문 보기</a>
      </div>
    </div>
  </section>
</main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self.send_bytes(b"ok\n", "text/plain; charset=utf-8")
            return
        if self.path.startswith("/logo.png"):
            self.send_bytes((BASE_DIR / "choice_ent_logo.png").read_bytes(), "image/png")
            return
        if self.path.startswith("/latest_report.png"):
            try:
                load_report()
                self.send_bytes(IMAGE_PATH.read_bytes(), "image/png")
            except Exception as exc:
                print(f"image error: {exc}")
                self.send_response(503)
                self.end_headers()
            return
        try:
            self.send_bytes(render_html().encode("utf-8"), "text/html; charset=utf-8")
        except Exception as exc:
            print(f"render error: {exc}")
            self.send_bytes(f"<pre>오류: {exc}</pre>".encode("utf-8"), "text/html; charset=utf-8")

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args)


def main() -> None:
    import threading
    port = int(os.environ.get("PORT", "8000"))
    print(f"Starting on port {port}")
    threading.Thread(target=_safe_preload, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Ready on port {port}")
    server.serve_forever()


def _safe_preload() -> None:
    try:
        load_report()
        print("Preload complete")
    except Exception as exc:
        print(f"Preload failed (non-fatal): {exc}")


if __name__ == "__main__":
    main()
