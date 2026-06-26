from __future__ import annotations

import base64
from collections.abc import Iterable
from html import escape
from pathlib import Path

import streamlit as st


def inject_global_style() -> None:
    support_images = _support_image_sources()
    support_cards = "".join(
        "<div class='support-qr-card'>"
        f"<img src='{src}' alt='{escape(label)} 收款码' />"
        f"<div>{escape(label)}</div>"
        "</div>"
        for label, src in support_images
    )
    html = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Noto+Serif+SC:wght@600;700&family=JetBrains+Mono:wght@500;700&display=swap');
        :root {
            --ink: #18211d;
            --muted: #647369;
            --paper: #fbfaf4;
            --panel: #eff5e9;
            --line: #d7e3d4;
            --green: #1a6f55;
            --red: #a23d31;
            --amber: #a06a16;
            --blue: #285f86;
            --copper: #b86f3d;
            --shadow: rgba(29, 48, 39, .14);
        }
        @keyframes riseIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes scanLine { from { transform: translateX(-20%); opacity: .12; } 50% { opacity: .34; } to { transform: translateX(120%); opacity: .12; } }
        @keyframes pulseRing { 0% { box-shadow: 0 0 0 0 rgba(26,111,85,.22); } 70% { box-shadow: 0 0 0 14px rgba(26,111,85,0); } 100% { box-shadow: 0 0 0 0 rgba(26,111,85,0); } }
        html, body, [class*="css"] {
            font-family: 'IBM Plex Sans', 'PingFang SC', sans-serif;
            color: var(--ink);
        }
        .stApp {
            background:
                radial-gradient(circle at 14% 6%, rgba(184,111,61,.22), transparent 25%),
                radial-gradient(circle at 88% 10%, rgba(40,95,134,.16), transparent 28%),
                radial-gradient(circle at 76% 78%, rgba(26,111,85,.12), transparent 26%),
                linear-gradient(135deg, #fbfaf4 0%, #eef5ea 50%, #f8efe2 100%);
        }
        .block-container { padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1520px; }
        h1, h2, h3 { font-family: 'Noto Serif SC', 'IBM Plex Sans', sans-serif; letter-spacing: 0; }
        h1 { font-size: 2.25rem !important; }
        div[data-testid="stDataFrame"] { border: 0; box-shadow: none; }
        div[data-testid="stMetric"] {
            background:
                linear-gradient(180deg, rgba(255,255,255,.92) 0%, rgba(243,247,239,.9) 100%);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: 0 12px 30px var(--shadow);
            animation: riseIn .35s ease both;
        }
        div[data-testid="stMetric"] label { color: var(--muted); }
        .stButton > button {
            border-radius: 10px;
            border: 1px solid #bfd1c2;
            font-weight: 650;
            transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 22px rgba(31, 111, 88, 0.14);
            border-color: var(--green);
        }
        .status-strip, .action-panel, .decision-card, .timeline, .hero-panel, .kpi-card, .insight-card, .query-ribbon, .smart-table-wrap, .link-card, .loading-panel, .chat-panel {
            border: 1px solid var(--line);
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.78);
            box-shadow: 0 18px 42px rgba(37, 53, 45, 0.08);
            backdrop-filter: blur(16px);
        }
        .status-strip {
            padding: 14px 16px;
            border-left: 5px solid var(--green);
            background: linear-gradient(90deg, #edf6f1 0%, #ffffff 80%);
            margin: 8px 0 18px;
        }
        .action-panel {
            padding: 16px 18px;
            background:
                linear-gradient(135deg, rgba(31, 111, 88, .10), rgba(255,255,255,.4)),
                repeating-linear-gradient(135deg, rgba(31,111,88,.035) 0 1px, transparent 1px 12px);
        }
        .decision-card {
            padding: 15px 17px;
            border-left: 4px solid var(--blue);
            margin: 8px 0;
        }
        .decision-card:hover, .kpi-card:hover, .link-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 22px 50px rgba(37, 53, 45, 0.13);
            transition: transform .16s ease, box-shadow .16s ease;
        }
        .hero-panel {
            position: relative;
            overflow: hidden;
            padding: 24px 28px;
            margin: 6px 0 18px;
            background:
                linear-gradient(120deg, rgba(25,35,31,.95), rgba(31,111,88,.86)),
                repeating-linear-gradient(135deg, rgba(255,255,255,.08) 0 1px, transparent 1px 14px);
            color: #f8fbf3;
        }
        .hero-panel:after {
            content: "";
            position: absolute;
            top: 0;
            bottom: 0;
            width: 42%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.12), transparent);
            animation: scanLine 5s ease-in-out infinite;
        }
        .hero-kicker {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            letter-spacing: .12em;
            text-transform: uppercase;
            opacity: .78;
        }
        .hero-title {
            font-family: 'Noto Serif SC', serif;
            font-size: 30px;
            line-height: 1.2;
            margin: 8px 0;
            font-weight: 700;
        }
        .hero-subtitle { max-width: 860px; color: rgba(248,251,243,.78); line-height: 1.7; }
        .hero-meta { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 8px; }
        .kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 10px 0 18px; }
        .kpi-card {
            padding: 15px 16px;
            border-left: 4px solid var(--green);
            animation: riseIn .4s ease both;
        }
        .kpi-label { color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: .04em; }
        .kpi-value { font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 800; margin-top: 5px; }
        .kpi-note { color: var(--muted); font-size: 12px; margin-top: 4px; }
        .insight-card { padding: 16px 18px; margin: 10px 0; }
        .insight-title { font-weight: 800; margin-bottom: 6px; }
        .insight-body { color: var(--muted); line-height: 1.65; font-size: 14px; }
        .query-ribbon { padding: 12px 14px; margin: 8px 0 14px; }
        .query-token {
            display: inline-flex;
            padding: 5px 9px;
            margin: 4px 5px 4px 0;
            border-radius: 999px;
            background: #f7efe4;
            color: #6d4529;
            border: 1px solid #e4cdb5;
            font-size: 12px;
            font-weight: 700;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 13px;
            font-weight: 650;
            border: 1px solid transparent;
            margin-right: 6px;
        }
        .badge-buy { color: #155b44; background: #e7f4ec; border-color: #b9dac4; }
        .badge-watch { color: #715013; background: #fff4d6; border-color: #ead08d; }
        .badge-risk { color: #8f2f25; background: #fff0ea; border-color: #e8b8ad; }
        .badge-neutral { color: #4d5d56; background: #eef2ef; border-color: #d2ddd5; }
        .timeline { padding: 12px 14px; }
        .timeline-step {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 0;
            border-bottom: 1px dashed #d6e1d8;
        }
        .timeline-step:last-child { border-bottom: 0; }
        .timeline-dot {
            width: 9px;
            height: 9px;
            border-radius: 999px;
            background: var(--green);
            box-shadow: 0 0 0 5px rgba(31, 111, 88, .12);
            flex: 0 0 9px;
        }
        .mini-note { color: var(--muted); font-size: 13px; line-height: 1.5; }
        .smart-table-wrap { overflow-x: auto; margin: 10px 0 18px; padding: 0; }
        table.smart-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 760px; }
        .smart-table th {
            position: sticky;
            top: 0;
            background: #eef5ea;
            color: #415149;
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid var(--line);
            font-weight: 800;
            white-space: nowrap;
        }
        .smart-table td {
            padding: 10px 12px;
            border-bottom: 1px solid rgba(215,227,212,.72);
            vertical-align: top;
            color: #223029;
        }
        .smart-table tr:hover td { background: rgba(26,111,85,.055); }
        .smart-table a { color: var(--blue); font-weight: 750; text-decoration: none; }
        .smart-table a:hover { text-decoration: underline; }
        .link-card { padding: 13px 15px; margin: 8px 0; border-left: 4px solid var(--green); }
        .link-card a { color: #173f32; text-decoration: none; font-weight: 850; }
        .link-card a:hover { color: var(--blue); text-decoration: underline; }
        .loading-panel {
            padding: 14px 16px;
            margin: 10px 0;
            border-left: 4px solid var(--green);
            background:
                linear-gradient(90deg, rgba(26,111,85,.11), rgba(255,255,255,.72)),
                repeating-linear-gradient(90deg, rgba(26,111,85,.035) 0 1px, transparent 1px 12px);
        }
        .loading-dot {
            display: inline-block;
            width: 9px;
            height: 9px;
            border-radius: 99px;
            background: var(--green);
            margin-right: 8px;
            animation: pulseRing 1.4s infinite;
        }
        .chat-panel { padding: 14px 16px; margin: 10px 0; border-left: 4px solid var(--copper); }
        .chat-answer { white-space: pre-wrap; line-height: 1.7; color: #26352d; }
        .support-toggle-input { display: none; }
        .support-fab {
            position: fixed;
            z-index: 9998;
            top: 14px;
            right: 18px;
            display: inline-flex;
            align-items: center;
            gap: 7px;
            border: 1px solid rgba(255,255,255,.38);
            border-radius: 999px;
            padding: 9px 13px;
            background:
                linear-gradient(135deg, rgba(25,35,31,.94), rgba(26,111,85,.9)),
                repeating-linear-gradient(135deg, rgba(255,255,255,.08) 0 1px, transparent 1px 10px);
            color: #f8fbf3;
            box-shadow: 0 16px 36px rgba(25,35,31,.20);
            font-size: 13px;
            font-weight: 850;
            cursor: pointer;
            user-select: none;
            transition: transform .16s ease, box-shadow .16s ease;
        }
        .support-fab:hover {
            transform: translateY(-1px);
            box-shadow: 0 22px 46px rgba(25,35,31,.28);
        }
        .support-backdrop {
            display: none;
            position: fixed;
            z-index: 9999;
            inset: 0;
            padding: 80px 18px 24px;
            background:
                radial-gradient(circle at 82% 18%, rgba(184,111,61,.24), transparent 22%),
                rgba(20, 29, 25, .54);
            backdrop-filter: blur(10px);
        }
        .support-toggle-input:checked ~ .support-backdrop { display: block; }
        .support-modal {
            max-width: 780px;
            margin: 0 auto;
            border: 1px solid rgba(255,255,255,.52);
            border-radius: 24px;
            background:
                linear-gradient(135deg, rgba(255,255,255,.96), rgba(244,249,240,.94)),
                repeating-linear-gradient(135deg, rgba(26,111,85,.035) 0 1px, transparent 1px 13px);
            box-shadow: 0 32px 86px rgba(12, 26, 18, .36);
            overflow: hidden;
        }
        .support-modal-head {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            padding: 20px 22px 12px;
            border-bottom: 1px solid var(--line);
        }
        .support-modal-title {
            font-family: 'Noto Serif SC', serif;
            font-size: 24px;
            font-weight: 800;
            color: var(--ink);
        }
        .support-modal-note {
            color: var(--muted);
            line-height: 1.65;
            font-size: 14px;
            margin-top: 4px;
        }
        .support-close {
            width: 34px;
            height: 34px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: #f8fbf3;
            color: var(--ink);
            cursor: pointer;
            font-weight: 900;
        }
        .support-qr-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
            padding: 18px 22px 22px;
        }
        .support-qr-card {
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 14px;
            background: rgba(255,255,255,.78);
            text-align: center;
            box-shadow: 0 14px 34px rgba(37,53,45,.10);
        }
        .support-qr-card img {
            width: min(100%, 280px);
            aspect-ratio: 1 / 1;
            object-fit: contain;
            border-radius: 14px;
            background: #fff;
        }
        .support-qr-card div {
            margin-top: 9px;
            color: var(--muted);
            font-size: 13px;
            font-weight: 800;
        }
        @media (max-width: 900px) {
            .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .hero-title { font-size: 24px; }
            .hero-panel { padding: 20px; }
            .support-fab { top: 10px; right: 10px; padding: 8px 11px; }
            .support-qr-grid { grid-template-columns: 1fr; }
        }
        </style>
        <input id="stock-support-toggle" class="support-toggle-input" type="checkbox" />
        <label for="stock-support-toggle" class="support-fab">支持项目</label>
        <div class="support-backdrop">
            <div class="support-modal">
                <div class="support-modal-head">
                    <div>
                        <div class="support-modal-title">支持 Stock Trend LLM</div>
                        <div class="support-modal-note">如果这个本地股票研究工具帮到了你，可以通过下面的收款码支持后续维护。感谢每一次认真反馈和支持。</div>
                    </div>
                    <label for="stock-support-toggle" class="support-close">x</label>
                </div>
                <div class="support-qr-grid">__SUPPORT_CARDS__</div>
            </div>
        </div>
        """.replace("__SUPPORT_CARDS__", support_cards)
    st.markdown(
        html,
        unsafe_allow_html=True,
    )


def _support_image_sources() -> list[tuple[str, str]]:
    root = Path(__file__).resolve().parents[1]
    images = [
        ("支持码 1", root / "assets" / "support" / "support_qr_1.jpg"),
        ("支持码 2", root / "assets" / "support" / "support_qr_2.jpg"),
    ]
    sources: list[tuple[str, str]] = []
    for label, path in images:
        try:
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
            sources.append((label, f"data:image/jpeg;base64,{payload}"))
        except Exception:
            continue
    return sources


def badge(label: str, tone: str = "neutral") -> str:
    css = {
        "buy": "badge-buy",
        "watch": "badge-watch",
        "risk": "badge-risk",
        "neutral": "badge-neutral",
    }.get(tone, "badge-neutral")
    return f"<span class='badge {css}'>{label}</span>"


def render_hero(title: str, subtitle: str, kicker: str = "Decision Workbench", badges: Iterable[tuple[str, str]] | None = None) -> None:
    meta = "".join(badge(label, tone) for label, tone in (badges or []))
    st.markdown(
        "<div class='hero-panel'>"
        f"<div class='hero-kicker'>{escape(kicker)}</div>"
        f"<div class='hero-title'>{escape(title)}</div>"
        f"<div class='hero-subtitle'>{escape(subtitle)}</div>"
        f"<div class='hero-meta'>{meta}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_kpi_grid(items: Iterable[tuple[str, str, str, str]]) -> None:
    html = ["<div class='kpi-grid'>"]
    for label, value, note, tone in items:
        color = {"buy": "var(--green)", "watch": "var(--amber)", "risk": "var(--red)", "neutral": "var(--blue)"}.get(tone, "var(--blue)")
        html.append(
            f"<div class='kpi-card' style='border-left-color:{color}'>"
            f"<div class='kpi-label'>{escape(label)}</div>"
            f"<div class='kpi-value'>{escape(value)}</div>"
            f"<div class='kpi-note'>{escape(note)}</div>"
            "</div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_insight(title: str, body: str, tone: str = "neutral") -> None:
    st.markdown(
        "<div class='insight-card'>"
        f"{badge(tone.upper(), tone if tone in {'buy', 'watch', 'risk', 'neutral'} else 'neutral')}"
        f"<div class='insight-title'>{escape(title)}</div>"
        f"<div class='insight-body'>{escape(body)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_query_ribbon(queries: Iterable[str], limit: int = 14) -> None:
    values = list(queries)
    shown = values[:limit]
    tokens = "".join(f"<span class='query-token'>{escape(item)}</span>" for item in shown)
    more = "" if len(values) <= limit else f"<span class='query-token'>+{len(values) - limit} more</span>"
    st.markdown(f"<div class='query-ribbon'>{tokens}{more}</div>", unsafe_allow_html=True)


def action_tone(action: str | None) -> str:
    if action in {"buy_candidate", "hold"}:
        return "buy"
    if action in {"avoid", "sell", "reduce"}:
        return "risk"
    if action in {"watch", "uncertain"}:
        return "watch"
    return "neutral"


def render_timeline(steps: Iterable[tuple[str, str]]) -> None:
    html = ["<div class='timeline'>"]
    for title, detail in steps:
        html.append(
            "<div class='timeline-step'>"
            "<span class='timeline-dot'></span>"
            f"<div><strong>{title}</strong><div class='mini-note'>{detail}</div></div>"
            "</div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_loading_panel(title: str, detail: str = "正在处理，请稍候...") -> None:
    st.markdown(
        "<div class='loading-panel'>"
        f"<span class='loading-dot'></span><strong>{escape(title)}</strong>"
        f"<div class='mini-note'>{escape(detail)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_static_table(rows: Iterable[dict], columns: list[str] | None = None, max_cell_length: int = 160) -> None:
    data = list(rows)
    if not data:
        st.info("暂无数据。")
        return
    columns = columns or list(data[0].keys())
    html = ["<div class='smart-table-wrap'><table class='smart-table'><thead><tr>"]
    html.extend(f"<th>{escape(str(col))}</th>" for col in columns)
    html.append("</tr></thead><tbody>")
    for row in data:
        html.append("<tr>")
        for col in columns:
            value = row.get(col, "")
            text = "" if value is None else str(value)
            if len(text) > max_cell_length:
                text = text[:max_cell_length] + "..."
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                cell = f"<a href='{escape(value)}' target='_blank' rel='noopener noreferrer'>打开链接</a>"
            else:
                cell = escape(text)
            html.append(f"<td>{cell}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_link_card(title: str, url: str, meta: str = "", tone: str = "neutral") -> None:
    tone_color = {"buy": "var(--green)", "watch": "var(--amber)", "risk": "var(--red)", "neutral": "var(--blue)"}.get(tone, "var(--blue)")
    safe_url = escape(url or "")
    if not safe_url:
        safe_url = "#"
    st.markdown(
        f"<div class='link-card' style='border-left-color:{tone_color}'>"
        f"<a href='{safe_url}' target='_blank' rel='noopener noreferrer'>{escape(title or '未命名链接')}</a>"
        f"<div class='mini-note'>{escape(meta)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_copy_button(label: str, text: str, key: str, helper: str = "") -> None:
    safe_key = "".join(ch if ch.isalnum() else "_" for ch in key)
    payload_id = f"copy_payload_{safe_key}"
    button_id = f"copy_button_{safe_key}"
    status_id = f"copy_status_{safe_key}"
    st.markdown(
        f"""
        <div class='decision-card'>
            <textarea id='{payload_id}' style='position:absolute; left:-9999px;'>{escape(text or "")}</textarea>
            <button id='{button_id}' style='
                border:1px solid #bfd1c2;
                border-radius:10px;
                padding:8px 12px;
                background:#f8fbf3;
                color:#173f32;
                font-weight:800;
                cursor:pointer;
            '>{escape(label)}</button>
            <span id='{status_id}' class='mini-note' style='margin-left:8px;'>{escape(helper)}</span>
        </div>
        <script>
        (function() {{
            const btn = document.getElementById("{button_id}");
            const payload = document.getElementById("{payload_id}");
            const status = document.getElementById("{status_id}");
            if (!btn || !payload || btn.dataset.bound === "1") return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", async function() {{
                const text = payload.value;
                try {{
                    await navigator.clipboard.writeText(text);
                    status.textContent = "已复制";
                }} catch (err) {{
                    payload.style.position = "fixed";
                    payload.style.left = "0";
                    payload.select();
                    document.execCommand("copy");
                    payload.style.position = "absolute";
                    payload.style.left = "-9999px";
                    status.textContent = "已复制";
                }}
                setTimeout(function() {{ status.textContent = "{escape(helper)}"; }}, 1600);
            }});
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )


def apply_chart_interaction(fig, *, y_title: str = "价格", x_title: str = "时间"):
    """Give Plotly charts a trading-terminal style hover/crosshair experience."""
    fig.update_layout(
        hovermode="x unified",
        dragmode="pan",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=12, r=12, t=52, b=24),
        hoverlabel=dict(bgcolor="rgba(25, 35, 31, .92)", font_size=12, font_color="#f8fbf3", bordercolor="#bfd1c2"),
        modebar=dict(orientation="h"),
    )
    fig.update_xaxes(
        title_text=x_title,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="#2f5f8f",
        spikethickness=1,
        showline=True,
        linecolor="#c9d7cd",
        showgrid=True,
        gridcolor="rgba(201, 215, 205, .45)",
    )
    fig.update_yaxes(
        title_text=y_title,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="#2f5f8f",
        spikethickness=1,
        showline=True,
        linecolor="#c9d7cd",
        showgrid=True,
        gridcolor="rgba(201, 215, 205, .45)",
    )
    for trace in fig.data:
        if getattr(trace, "type", "") == "scatter":
            trace.update(mode="lines+markers", marker=dict(size=5))
        elif getattr(trace, "type", "") == "bar":
            trace.update(hovertemplate="%{x}<br>%{y:,.2f}<extra>%{fullData.name}</extra>")
        elif getattr(trace, "type", "") == "candlestick":
            trace.update(
                increasing_line_color="#1f6f58",
                decreasing_line_color="#a94335",
                hovertext=None,
                hovertemplate=(
                    "日期 %{x}<br>"
                    "开 %{open:.2f}<br>"
                    "高 %{high:.2f}<br>"
                    "低 %{low:.2f}<br>"
                    "收 %{close:.2f}<extra>K线</extra>"
                ),
            )
    return fig
