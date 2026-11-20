"""SERENX - Doctor-Patient Wellness Platform (Streamlit frontend).

The FastAPI backend is started automatically in a background thread, so the whole
app deploys as ONE Streamlit app. Set BACKEND_URL to use an external backend instead.
"""
import html as _html
import os
import random
import time
import uuid
from datetime import date, timedelta
from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="SERENX", page_icon=":material/spa:", layout="wide")

# Streamlit Cloud secrets -> environment (so the backend can read the API key)
try:
    for _k in ("ANTHROPIC_API_KEY", "AI_MODEL", "BACKEND_URL"):
        if _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
PORT = int(os.getenv("BACKEND_PORT", "8765"))
API = BACKEND_URL or f"http://127.0.0.1:{PORT}"
TAGLINE = "Your Wellness, Our Priority."
SUBLINE = "Personalized care for a healthier tomorrow."
DISCLAIMER = ("AI-generated summary for information only. It is not a medical diagnosis and "
              "not a treatment decision. Always review the original answers.")
COMPANION_NOTE = ("The companion is an AI for general wellness support. It is not a doctor or therapist and cannot "
                  "diagnose or treat anything. Your doctor cannot see your chats or journal.")
MOOD_LABELS = {1: "Very low", 2: "Low", 3: "Okay", 4: "Good", 5: "Great"}
MOOD_EMOJI = {1: "😞", 2: "😕", 3: "😐", 4: "🙂", 5: "😄"}
MOOD_COLORS = {1: ("#F8CFCB", "#A8302A"), 2: ("#FFE3B0", "#855A00"), 3: ("#E6F0CE", "#587012"),
               4: ("#8FCB74", "#14400A"), 5: ("#2F4F1E", "#FFFFFF")}
try:  # optional: browser speech-to-text (Chrome / Edge). Falls back to typing when missing.
    from streamlit_mic_recorder import speech_to_text
except Exception:  # pragma: no cover
    speech_to_text = None

FREQ_LABEL = {"once": "One-time", "daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
FREQ_TONE = {"once": "teal", "daily": "forest", "weekly": "leaf", "monthly": "sun"}


@st.cache_resource(show_spinner="Starting the app...")
def start_backend() -> bool:
    if BACKEND_URL:
        return True
    import threading

    import uvicorn

    from backend.main import app as api_app

    server = uvicorn.Server(uvicorn.Config(api_app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(150):
        try:
            if requests.get(f"{API}/health", timeout=1).ok:
                return True
        except requests.RequestException:
            time.sleep(0.2)
    return False


if not start_backend():
    st.error("The backend could not start. Please refresh the page.")
    st.stop()


# ------------------------------------------------------------------ API helpers
class ApiError(Exception):
    pass


def api(method: str, path: str, **kw):
    headers = {}
    if st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        r = requests.request(method, API + path, headers=headers, timeout=90, **kw)
    except requests.RequestException:
        raise ApiError("Cannot reach the server. Please try again.")
    if r.status_code == 401 and st.session_state.get("token"):
        st.session_state.clear()
        st.rerun()
    if not r.ok:
        try:
            detail = r.json().get("detail", "Something went wrong.")
        except ValueError:
            detail = "Something went wrong."
        if isinstance(detail, list):  # pydantic validation errors
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        raise ApiError(str(detail))
    return r.json()


def get(path: str):
    """GET that stops the page with a friendly error instead of a traceback."""
    try:
        return api("GET", path)
    except ApiError as e:
        st.error(str(e))
        st.stop()


def post(path: str, body: dict | None = None, ok_msg: str | None = None):
    """POST for button actions. Returns data or None on error."""
    try:
        data = api("POST", path, json=body or {})
        if ok_msg:
            st.success(ok_msg)
        return data
    except ApiError as e:
        st.error(str(e))
        return None


# ================================================================== DESIGN SYSTEM
# Forest-green wellness look. Icons, waves and the forest scene are all drawn in code
# (CSS masks / generated SVG), so there are no emojis and no image files.
ICONS = {
    "clipboard": '<rect x="5" y="4" width="14" height="17" rx="3"/><path d="M9 4.5h6M9 11h6M9 15h4"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "flame": '<path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z"/>',
    "bolt": '<path d="M13 3 5 13h6l-1 8 8-10h-6z"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2-5.5-3-5.5 3 1-6.2L3 9.6l6.2-.9z"/>',
    "leaf": '<path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15"/><path d="M5 19c3-5 6-7 9-8"/>',
    "pen": '<path d="M4 20l4-1 11-11-3-3L5 16z"/><path d="m14 7 3 3"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.5 3-6 6.5-6s6.5 2.5 6.5 6"/>'
             '<circle cx="17.5" cy="9" r="2.5"/><path d="M17 14c2.8 0 4.5 2 4.5 4.5"/>',
    "home": '<path d="M4 11 12 4l8 7v9H4z"/><path d="M10 20v-5h4v5"/>',
    "trend": '<path d="M3 17l6-6 4 4 7-8"/><path d="M15 7h5v5"/>',
    "check": '<path d="m5 12 4.5 4.5L19 7"/>',
    "alert": '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17h.01"/>',
    "calendar": '<rect x="4" y="5" width="16" height="16" rx="3"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    "heart": '<path d="M12 20s-8-5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 9c0 6-8 11-8 11z"/>',
    "shield": '<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
    "send": '<path d="M21 3 3 10l7 3 3 7z"/><path d="m10 13 11-10"/>',
    "sparkle": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 17v4M17 19h4"/>',
}

TONES = {  # tone -> (solid, soft background, strong text)
    "forest": ("#2F4F1E", "#E1F1D3", "#2F4F1E"),
    "leaf": ("#4FAE35", "#DDF5CE", "#2B7A17"),
    "teal": ("#2E9C8F", "#D5F1EC", "#16665C"),
    "lime": ("#8DB63C", "#EBF5CF", "#587012"),
    "sun": ("#E2A82B", "#FFF1CC", "#855A00"),
    "coral": ("#E5584F", "#FDE3E0", "#A8302A"),
}
AVATAR_TONES = ["forest", "leaf", "teal", "lime", "sun"]


def _icon_css() -> str:
    root, rules = [], []
    for k, v in ICONS.items():
        svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
               f"stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{v}</svg>")
        root.append(f"--ico-{k}:url(\"data:image/svg+xml,{quote(svg)}\");")
        rules.append(f".ic-{k}{{--m:var(--ico-{k})}}")
    return ":root{" + "".join(root) + "}" + "".join(rules)


def _tone_css() -> str:
    out = []
    for t, (solid, soft, strong) in TONES.items():
        out.append(f".solid-{t}{{background:{solid};color:#fff}}.soft-{t}{{background:{soft};color:{strong}}}")
    return "".join(out)


def _waves(opacity: float = .4) -> str:
    """Thin flowing lines like the corners of a wellness app splash screen."""
    paths = "".join(
        f"<path d='M-60 {70 + i * 7} C 140 {-30 + i * 7}, 300 {190 + i * 7}, 520 {50 + i * 7} "
        f"S 780 {10 + i * 7}, 940 {100 + i * 7}'/>" for i in range(16))
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 900 260' fill='none' stroke='#3F8A2A' "
           f"stroke-opacity='{opacity}' stroke-width='1'>{paths}</svg>")
    return "data:image/svg+xml," + quote(svg)


def _forest() -> str:
    """Layered misty pine forest (generated, original artwork)."""
    r = random.Random(11)
    out = []
    for color, op, base, s in (("#6FA062", .32, 150, .75), ("#35663A", .55, 185, .9),
                               ("#143820", .85, 222, 1.1), ("#0A1F0F", 1.0, 258, 1.3)):
        x = -10.0
        while x < 420:
            h = r.uniform(95, 150) * s * .7
            w = h * .36
            polys = ""
            for t in range(5):
                top = base - h + t * h * .17
                half = w * (.35 + .16 * t)
                polys += (f"<polygon points='{x:.0f},{top:.0f} {x - half:.0f},{top + h * .3:.0f} "
                          f"{x + half:.0f},{top + h * .3:.0f}'/>")
            out.append(f"<g fill='{color}' fill-opacity='{op}'>{polys}<rect x='{x - 2:.0f}' y='{base - 8}' width='4' height='50'/></g>")
            x += r.uniform(26, 46) / s ** .5
        out.append(f"<rect x='0' y='{base + 8}' width='400' height='300' fill='{color}' fill-opacity='{op}'/>")
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 300' preserveAspectRatio='xMidYMax slice'>"
           + "".join(out) + "</svg>")
    return "data:image/svg+xml," + quote(svg)


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');
:root{--ink:#1B3318;--muted:#6E8268;--line:#D9EBCB;--forest:#2F4F1E;--leaf:#4C8B2B;--fresh:#5CBF3A;--mint:#E1F1D3;
 --shadow:0 6px 22px rgba(47,79,30,.09);}
html,body,.stApp,[class*="css"],button,input,textarea,select{font-family:'Poppins',system-ui,-apple-system,'Segoe UI',sans-serif!important;}
.stApp{color:var(--ink);background:url("__WAVE__") no-repeat left -60px top -40px/860px auto,
 url("__WAVE__") no-repeat right -80px bottom -60px/900px auto,
 linear-gradient(160deg,#E4F6D3 0%,#F6FBF1 36%,#FFFFFF 62%,#E8F6DB 100%);background-attachment:fixed;}
[data-testid="stToolbar"],[data-testid="stDecoration"],footer,#MainMenu{display:none!important;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:1.4rem;padding-bottom:8.5rem;max-width:940px;}
h1,h2,h3,h4{color:var(--ink);letter-spacing:-.01em;}
.ic{display:inline-block;width:1.15em;height:1.15em;vertical-align:-.2em;background:currentColor;
 -webkit-mask:var(--m) center/contain no-repeat;mask:var(--m) center/contain no-repeat;}

/* ---------- top bar + floating bottom navigation ---------- */
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"]{display:none!important;}
.logo{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;border:2px solid rgba(255,255,255,.92);flex:none;}
.logo .ic{width:20px;height:20px;}
.brandrow{display:flex;align-items:center;gap:10px;font-weight:700;letter-spacing:.22em;font-size:.82rem;color:var(--forest);margin-bottom:14px;}
.brandrow .logo{width:30px;height:30px;border-color:var(--forest);}
.brandrow .logo .ic{width:15px;height:15px;}
.st-key-topbar [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.6rem!important;align-items:center;}
.st-key-topbar [data-testid="stColumn"]{min-width:0!important;}
.st-key-topbar [data-testid="stColumn"]:first-child{flex:1 1 auto!important;width:auto!important;}
.st-key-topbar [data-testid="stColumn"]:last-child{flex:0 0 auto!important;width:auto!important;}
.st-key-topbar .stButton>button{padding:.45rem 1.1rem;font-size:.84rem;background:#fff;box-shadow:var(--shadow);}
.st-key-navbar{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);z-index:999;width:max-content!important;max-width:calc(100vw - 16px);
 background:rgba(255,255,255,.97);border-radius:36px;padding:8px 10px;box-shadow:0 14px 36px rgba(30,60,20,.26);}
.st-key-navbar [data-testid="stRadio"]{width:auto;}
.st-key-navbar [data-testid="stRadioGroup"]{flex-direction:row!important;flex-wrap:nowrap!important;gap:2px!important;}
.st-key-navbar [data-testid="stRadioOption"]{position:relative;display:flex;flex-direction:column;align-items:center;gap:3px;
 min-width:70px;padding:6px 6px 4px;margin:0;cursor:pointer;border-radius:24px;}
.st-key-navbar [data-testid="stRadioOption"] > div > div:first-child{display:none!important;}
.st-key-navbar [data-testid="stRadioOption"] > div{text-align:center;margin:0!important;padding:0!important;}
.st-key-navbar [data-testid="stRadioOption"]::before{content:"";width:54px;height:34px;border-radius:99px;background:transparent;transition:background .15s;}
.st-key-navbar [data-testid="stRadioOption"]::after{content:"";position:absolute;top:13px;left:50%;margin-left:-10px;width:20px;height:20px;
 background:#73886B;-webkit-mask:var(--m) center/contain no-repeat;mask:var(--m) center/contain no-repeat;}
.st-key-navbar [data-testid="stRadioOption"] p{font-size:.7rem!important;font-weight:600;color:#73886B;margin:0;line-height:1.2;white-space:nowrap;}
.st-key-navbar [data-testid="stRadioOption"][data-selected="true"]::before{background:#2F4F1E;}
.st-key-navbar [data-testid="stRadioOption"][data-selected="true"]::after{background:#fff;}
.st-key-navbar [data-testid="stRadioOption"][data-selected="true"] p{color:#2F4F1E;font-weight:700;}

/* ---------- home header, progress card, insight, timeline ---------- */
.top{display:flex;align-items:center;gap:14px;}
.top .hi{font-size:.85rem;color:var(--muted);font-weight:500;}
.top b{font-size:1.45rem;font-weight:700;line-height:1.15;color:var(--ink);}
.card{background:#fff;border-radius:26px;padding:20px 22px;box-shadow:var(--shadow);margin-bottom:16px;}
.card .ph{display:flex;align-items:center;gap:12px;font-weight:700;font-size:1.02rem;}
.card .ph b{margin-left:auto;font-size:1.05rem;color:var(--forest);}
.pbar{height:12px;border-radius:99px;background:#E6EEDF;margin:14px 0 10px;overflow:hidden;}
.pbar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#2F4F1E,#5CBF3A);}
.card .pc{font-size:.85rem;color:var(--muted);font-weight:500;}
.insight{display:flex;align-items:center;gap:18px;padding:18px 24px;border-radius:34px;margin-bottom:18px;
 background:linear-gradient(120deg,#122E16 0%,#1F4A1F 60%,#2B6425 100%);box-shadow:0 12px 26px rgba(20,56,24,.28);}
.insight *{color:#fff;}
.orb{width:46px;height:46px;border-radius:50%;flex:none;background:radial-gradient(circle at 35% 30%,#F4FF8A,#63E04A 55%,#1F9B3B);
 box-shadow:0 0 22px rgba(130,255,90,.65);}
.insight .k{font-size:.8rem;font-weight:700;}
.insight .k span{font-weight:500;opacity:.75;margin-left:6px;}
.insight .tx{font-size:.95rem;line-height:1.4;margin-top:2px;opacity:.95;}
.tl{background:#fff;border-radius:26px;padding:22px 22px 6px;box-shadow:var(--shadow);margin-bottom:18px;}
.tli{position:relative;padding:0 0 22px 48px;min-height:30px;}
.tli::before{content:"";position:absolute;left:13px;top:30px;bottom:-4px;border-left:2px dashed #B8D6A6;}
.tli:last-child::before{display:none;}
.tdot{position:absolute;left:0;top:1px;width:28px;height:28px;border-radius:50%;border:2px solid #8A9C82;background:#fff;box-sizing:border-box;}
.tli.done .tdot{background:#4DB83A;border-color:#4DB83A;color:#fff;display:grid;place-items:center;}
.tli.done .tdot .ic{width:15px;height:15px;}
.tli .t{font-weight:600;font-size:1rem;color:var(--ink);line-height:1.3;}
.tli .m{font-size:.8rem;color:var(--muted);margin-top:2px;}
.tli.done .t{text-decoration:line-through;color:var(--muted);}

/* ---------- tiles, rows, pills ---------- */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:20px;}
.tile{background:#fff;border-radius:24px;padding:16px 18px;box-shadow:var(--shadow);}
.tile b{display:block;font-size:1.75rem;font-weight:700;line-height:1.1;margin-top:12px;color:var(--ink);}
.tile span.l{font-size:.8rem;font-weight:500;color:var(--muted);}
.chip{width:40px;height:40px;border-radius:14px;display:inline-grid;place-items:center;flex:none;}
.chip .ic{width:20px;height:20px;}
.sec{font-size:1.15rem;font-weight:700;margin:26px 0 12px;color:var(--ink);}
.secsub{font-weight:500;color:var(--muted);font-size:.82rem;margin-left:8px;}
.row{display:flex;align-items:center;gap:14px;background:#fff;border-radius:22px;padding:14px 16px;margin-bottom:10px;box-shadow:var(--shadow);}
.row .main{flex:1;min-width:0;}
.row .t{font-weight:600;font-size:.97rem;line-height:1.3;color:var(--ink);}
.row .m{font-size:.8rem;color:var(--muted);margin-top:3px;}
.row .end{font-weight:700;font-size:.92rem;color:var(--forest);text-align:right;}
.pill{display:inline-block;padding:3px 11px;border-radius:99px;font-size:.73rem;font-weight:600;margin-right:6px;}
.bar{height:8px;border-radius:99px;background:#E6EEDF;margin-top:9px;overflow:hidden;}
.bar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#2F4F1E,#5CBF3A);}
.av{border-radius:50%;display:grid;place-items:center;font-weight:700;flex:none;color:#fff;}
.alert{background:#FDE9E6;border-radius:24px;padding:16px 18px;margin-bottom:10px;display:flex;gap:14px;align-items:flex-start;}
.alert .t{font-weight:700;color:#9E2B2B;}
.alert ul{margin:6px 0 0;padding-left:18px;color:#9E2B2B;font-size:.86rem;}
.okbox{background:#DDF5CE;color:#2B6B17;border-radius:24px;padding:16px 20px;display:flex;gap:12px;align-items:center;font-weight:600;}
.doccard{display:flex;gap:16px;align-items:center;background:#fff;border-radius:26px;padding:18px;margin-bottom:18px;box-shadow:var(--shadow);}
.doccard .t{font-weight:700;font-size:1.05rem;}
.doccard .m{color:var(--muted);font-size:.84rem;margin-top:2px;}
.badges{display:grid;grid-template-columns:repeat(auto-fill,minmax(106px,1fr));gap:12px;}
.bd{background:#fff;border-radius:24px;padding:16px 8px 14px;text-align:center;box-shadow:var(--shadow);}
.bd .chip{width:52px;height:52px;border-radius:50%;margin:0 auto 8px;}
.bd .chip .ic{width:26px;height:26px;}
.bd b{display:block;font-size:.8rem;font-weight:600;}
.bd span{font-size:.7rem;color:var(--muted);}
.bd.off{opacity:.5;filter:grayscale(1);}
.empty{background:#fff;border-radius:24px;padding:26px;text-align:center;color:var(--muted);font-weight:500;box-shadow:var(--shadow);}
.flag{color:#C23B3B;font-weight:600;}
.ainote{display:inline-flex;align-items:center;gap:6px;font-weight:600;font-size:.83rem;color:var(--forest);background:var(--mint);padding:5px 12px;border-radius:99px;margin:4px 0 8px;}

/* ---------- login screen ---------- */
.authhero{border-radius:34px;padding:34px 30px 250px;color:#fff;min-height:560px;position:relative;overflow:hidden;
 background:__FOREST__ center bottom/100% 250px no-repeat,
 radial-gradient(circle at 72% 18%,rgba(170,240,120,.38),transparent 46%),
 linear-gradient(180deg,#245A26 0%,#14321A 70%,#0A1F0F 100%);box-shadow:0 20px 44px rgba(20,56,24,.3);}
.authhero *{color:#fff;}
.authhero .word{font-size:2.5rem;font-weight:800;letter-spacing:.14em;margin:18px 0 4px;line-height:1.1;}
.authhero h1{font-size:1.35rem;font-weight:600;margin:0 0 6px;line-height:1.3;}
.authhero p{opacity:.88;font-size:.95rem;margin:0 0 6px;}
.feat{display:flex;gap:12px;align-items:center;margin-top:14px;font-weight:500;font-size:.92rem;}
.authhero .chip{background:rgba(255,255,255,.18);color:#fff;}
.authhero .logo{width:46px;height:46px;}
.demo{display:flex;align-items:center;gap:12px;background:#fff;border-radius:20px;padding:10px 14px;margin-bottom:8px;box-shadow:var(--shadow);}
.demo b{font-size:.88rem;font-weight:600;}
.demo span.m{display:block;font-size:.77rem;color:var(--muted);}

/* ---------- native widgets ---------- */
[data-testid="stTextInputRootElement"],[data-testid="stNumberInputContainer"],[data-testid="stSelectbox"] [role="group"],
[data-testid="stDateInputField"],[data-testid="stMultiSelect"] [role="group"],[data-testid="stTextArea"] [data-baseweb="textarea"]{
 background:#fff!important;border:1.5px solid var(--line)!important;border-radius:16px!important;box-shadow:none!important;}
[data-testid="stTextInputRootElement"] input,[data-testid="stNumberInputContainer"] input,[data-testid="stSelectbox"] input,
[data-testid="stTextArea"] textarea{background:transparent!important;border:none!important;color:var(--ink)!important;box-shadow:none!important;}
[data-testid="stTextInputRootElement"]:focus-within,[data-testid="stSelectbox"] [role="group"]:focus-within,
[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,[data-testid="stNumberInputContainer"]:focus-within{
 border-color:var(--leaf)!important;box-shadow:0 0 0 3px rgba(76,139,43,.2)!important;}
[data-testid="stForm"]{background:#fff;border:none;border-radius:28px;padding:22px;box-shadow:var(--shadow);}
.stButton>button,[data-testid="stFormSubmitButton"]>button{border-radius:99px;font-weight:600;padding:.62rem 1.4rem;border:1.5px solid var(--line);background:#fff;color:var(--forest);}
.stButton>button[kind="primary"],[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"]{
 background:#2F4F1E!important;border:none!important;color:#fff!important;box-shadow:0 10px 20px rgba(47,79,30,.3);}
.stButton>button[kind="primary"]:hover,[data-testid="stBaseButton-primary"]:hover,[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:#3C6326!important;}
[data-testid="stExpander"]{background:#fff;border:none!important;border-radius:22px;box-shadow:var(--shadow);margin-bottom:10px;overflow:hidden;}
[data-testid="stExpander"] summary{font-weight:600;padding:.9rem 1.1rem;}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:26px;background:#fff;border:none!important;box-shadow:var(--shadow);}
[data-testid="stTabs"] [role="tablist"]{gap:4px;background:rgba(47,79,30,.08)!important;border:none!important;box-shadow:none!important;
 margin-bottom:14px;flex-wrap:wrap;border-radius:99px;padding:5px;width:fit-content;max-width:100%;}
[data-testid="stTabs"] [data-orientation="horizontal"]{border:none!important;box-shadow:none!important;}
[data-testid="stTabs"] [role="tablist"]::before,[data-testid="stTabs"] [role="tablist"]::after{display:none!important;}
[data-testid="stTab"]{background:transparent;border-radius:99px;padding:8px 18px;height:auto;border:none!important;box-shadow:none;}
[data-testid="stTab"] p{color:var(--muted);font-weight:600;}
[data-testid="stTab"][aria-selected="true"]{background:#fff;box-shadow:0 3px 10px rgba(30,60,20,.14);}
[data-testid="stTab"][aria-selected="true"] p{color:var(--forest);}
.react-aria-SelectionIndicator,[data-testid="stTabs"] [data-baseweb="tab-highlight"],[data-testid="stTabs"] [data-baseweb="tab-border"]{display:none!important;}
[data-testid="stSlider"] [role="slider"]{background:var(--leaf);box-shadow:0 0 0 4px rgba(76,139,43,.22);}
[data-testid="stAlert"]{border-radius:20px;border:none;}
[data-testid="stDataFrame"]{border-radius:20px;overflow:hidden;}
@media (max-width:640px){
 .block-container{padding-left:1rem;padding-right:1rem;}
 .authhero{min-height:0;padding:24px 22px 175px;background-size:100% 175px,auto,auto;} .authhero .word{font-size:2rem;}
 [data-testid="stTabs"] [role="tablist"]{flex-wrap:nowrap;width:100%;overflow-x:auto;}
 [data-testid="stTab"]{padding:8px 11px;white-space:nowrap;} [data-testid="stTab"] p{font-size:.76rem;}
 .top b{font-size:1.2rem;}
 .stApp{background:url("__WAVEL__") no-repeat left -90px top -70px/520px auto,
  linear-gradient(160deg,#E4F6D3 0%,#F6FBF1 40%,#FFFFFF 70%,#EAF6DE 100%);background-attachment:fixed;}
 .st-key-navbar{padding:6px 6px;}
 .st-key-navbar [data-testid="stRadioOption"]{min-width:0;padding:6px 5px 4px;}
 .st-key-navbar [data-testid="stRadioOption"]::before{width:46px;}
 .st-key-navbar [data-testid="stRadioOption"]::after{margin-left:-10px;}
 .st-key-navbar [data-testid="stRadioOption"] p{font-size:.64rem!important;}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;}}
"""


CSS_EXTRA = """
.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;background:#fff;border-radius:26px;padding:14px;box-shadow:var(--shadow);margin-bottom:6px;}
.cal .h{text-align:center;font-size:.68rem;font-weight:600;color:var(--muted);padding-bottom:2px;}
.cal .d{aspect-ratio:1/1;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:600;color:#B3C2AC;background:#F4F8F0;}
.cal .d{position:relative;}
.cal .d .n{position:absolute;top:4px;left:7px;font-size:.58rem;font-weight:700;opacity:.75;}
.cal .d .em{font-size:1.25rem;line-height:1;margin-top:5px;}
[data-testid="stButtonGroup"] button,[data-testid="stButtonGroup"] button *{font-size:1.55rem!important;line-height:1.2;}
[data-testid="stButtonGroup"] button{padding:6px 4px!important;min-height:52px;}
.cal .d.today{outline:2px solid #2F4F1E;outline-offset:1px;}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:.74rem;color:var(--muted);margin:8px 4px 16px;}
.legend i{display:inline-block;width:11px;height:11px;border-radius:4px;margin-right:5px;vertical-align:-1px;}
.monthlbl{text-align:center;font-weight:700;color:var(--forest);font-size:1.02rem;}
.chat{display:flex;flex-direction:column;gap:10px;margin:6px 0 14px;}
.chat .b{max-width:86%;padding:12px 16px;border-radius:20px;font-size:.92rem;line-height:1.45;word-wrap:break-word;}
.chat .u{align-self:flex-end;background:#2F4F1E;color:#fff;border-bottom-right-radius:6px;}
.chat .a{align-self:flex-start;background:#fff;color:var(--ink);box-shadow:var(--shadow);border-bottom-left-radius:6px;}
.chat .c{background:#FDE3E0;color:#A8302A;}
.crisis{background:#FDE3E0;color:#A8302A;border-radius:20px;padding:14px 18px;font-size:.92rem;line-height:1.5;margin:8px 0 12px;}
[data-testid="InputInstructions"]{display:none!important;}
.jentry .when{font-size:.78rem;color:var(--muted);margin-bottom:4px;}
"""


def inject_css(nav_icons: list[str] | None = None):
    nav = ""
    for i, name in enumerate(nav_icons or [], 1):
        nav += (f".st-key-navbar [data-testid='stRadioGroup'] > div:nth-child({i}) "
                f"[data-testid='stRadioOption']{{--m:var(--ico-{name});}}")
    css = (CSS + CSS_EXTRA).replace("__WAVEL__", _waves(.2)).replace("__WAVE__", _waves()).replace("__FOREST__", f'url("{_forest()}")')
    st.markdown(f"<style>{_icon_css()}{_tone_css()}{css}{nav}</style>", unsafe_allow_html=True)


# ------------------------------------------------------------------ small UI helpers
def esc(x) -> str:
    return _html.escape(str(x if x is not None else ""))


def md(s: str):
    """Render an HTML snippet (collapsed to one block so Markdown never treats it as code)."""
    st.markdown(" ".join(line.strip() for line in s.strip().splitlines()), unsafe_allow_html=True)


def icon(name: str) -> str:
    return f"<i class='ic ic-{name}'></i>"


def chip(name: str, tone: str) -> str:
    return f"<span class='chip soft-{tone}'>{icon(name)}</span>"


def pill(text: str, tone: str) -> str:
    return f"<span class='pill soft-{tone}'>{esc(text)}</span>"


def avatar(name: str, size: int = 44) -> str:
    parts = [p for p in name.replace(".", " ").split() if p.lower() not in ("dr",)] or [name]
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
    tone = AVATAR_TONES[sum(map(ord, name)) % len(AVATAR_TONES)]
    return (f"<span class='av solid-{tone}' style='width:{size}px;height:{size}px;"
            f"font-size:{int(size * .36)}px'>{esc(initials)}</span>")


def tile(label: str, value, tone: str, ic: str) -> str:
    return f"<div class='tile'>{chip(ic, tone)}<b>{esc(value)}</b><span class='l'>{esc(label)}</span></div>"


def tiles(items: list[tuple]):
    md("<div class='tiles'>" + "".join(tile(*i) for i in items) + "</div>")


def progress_card(title: str, pct: int | None, caption: str, ic: str = "trend"):
    p = max(0, min(100, int(pct or 0)))
    shown = f"{p}%" if pct is not None else "-"
    md(f"<div class='card'><div class='ph'>{chip(ic, 'forest')}{esc(title)}<b>{shown}</b></div>"
       f"<div class='pbar'><i style='width:{p}%'></i></div><div class='pc'>{esc(caption)}</div></div>")


def insight(text: str, tag: str = "Smart tip"):
    md(f"<div class='insight'><span class='orb'></span><div><div class='k'>Insight<span>{esc(tag)}</span></div>"
       f"<div class='tx'>{esc(text)}</div></div></div>")


def timeline(items: list[tuple]):
    """items: (title, subtitle, done)"""
    html_items = ""
    for title, sub, done in items:
        dot = icon("check") if done else ""
        html_items += (f"<div class='tli {'done' if done else ''}'><span class='tdot'>{dot}</span>"
                       f"<div class='t'>{esc(title)}</div><div class='m'>{esc(sub)}</div></div>")
    md(f"<div class='tl'>{html_items}</div>")


def section(title: str, sub: str = ""):
    s = f"<span class='secsub'>{esc(sub)}</span>" if sub else ""
    md(f"<div class='sec'>{esc(title)}{s}</div>")


def row(ic: str, tone: str, title: str, meta: str = "", pills: str = "", end: str = ""):
    md(f"<div class='row'>{chip(ic, tone)}<div class='main'><div class='t'>{esc(title)}</div>"
       f"<div class='m'>{pills}{esc(meta)}</div></div><div class='end'>{esc(end)}</div></div>")


def empty(text: str):
    md(f"<div class='empty'>{esc(text)}</div>")


def ai_tag(text: str = "AI summary"):
    md(f"<span class='ainote'>{icon('sparkle')}{esc(text)}</span>")


def fmt_date(s: str) -> str:
    try:
        return date.fromisoformat(s[:10]).strftime("%d %b %Y")
    except ValueError:
        return s


def show_answers(answers: list[dict]):
    for a in answers:
        val = a["answer"] if str(a["answer"]).strip() else "No answer"
        if a["qtype"] == "rating" and val != "No answer":
            val = f"{val} / 5"
        st.markdown(f"**{a['question']}**  \n{val}")


def trend_chart(trend: list[dict]):
    if not trend:
        empty("No rating answers yet. The mood chart appears after the first assessment.")
        return
    df = pd.DataFrame(trend).groupby("date", as_index=False)["value"].mean()
    df["date"] = pd.to_datetime(df["date"])
    base = alt.Chart(df).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%d %b", labelColor="#6E8268", grid=False,
                                                     domain=False, tickCount=6)),
        y=alt.Y("value:Q", title=None, scale=alt.Scale(domain=[1, 5], clamp=True, nice=False),
                axis=alt.Axis(values=[1, 2, 3, 4, 5], labelColor="#6E8268", gridColor="#E6F0DD", domain=False)),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%d %b"),
                 alt.Tooltip("value:Q", title="Average rating", format=".1f")],
    )
    area = base.mark_area(
        interpolate="monotone", line=False,
        color=alt.Gradient(gradient="linear", stops=[alt.GradientStop(color="rgba(76,139,43,0.38)", offset=0),
                                                     alt.GradientStop(color="rgba(76,139,43,0.0)", offset=1)],
                           x1=1, x2=1, y1=1, y2=0)).encode(y2=alt.datum(1))
    line = base.mark_line(interpolate="monotone", color="#2F6B22", strokeWidth=3.5)
    dots = base.mark_circle(color="#fff", stroke="#2F6B22", strokeWidth=2.5, size=70, opacity=1)
    chart = (area + line + dots).properties(height=260).configure_view(strokeWidth=0).configure(background="transparent")
    with st.container(border=True):
        st.altair_chart(chart, width="stretch")


def badge_grid(badges: list[dict]):
    tones = ["leaf", "sun", "forest", "teal", "lime", "coral"]
    cards = ""
    for i, b in enumerate(badges):
        cards += (f"<div class='bd {'' if b['earned'] else 'off'}'>{chip(b['icon'], tones[i % len(tones)])}"
                  f"<b>{esc(b['name'])}</b><span>{esc(b['desc'])}</span></div>")
    md(f"<div class='badges'>{cards}</div>")


def crisis_box(text: str):
    md(f"<div class='crisis'>{esc(text)}</div>")


def month_nav(scope: str) -> str:
    """Prev / next month controls. Returns 'YYYY-MM'."""
    key = f"{scope}_off"
    off = st.session_state.setdefault(key, 0)
    c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="center")
    with c1:
        if st.button("Previous", key=f"{scope}_prev", width="stretch"):
            st.session_state[key] = off - 1
            st.rerun()
    with c3:
        if st.button("Next", key=f"{scope}_next", width="stretch", disabled=off >= 0):
            st.session_state[key] = off + 1
            st.rerun()
    t = date.today()
    y, m = divmod(t.year * 12 + t.month - 1 + off, 12)
    with c2:
        md(f"<div class='monthlbl'>{date(y, m + 1, 1).strftime('%B %Y')}</div>")
    return f"{y}-{m + 1:02d}"


def mood_calendar(data: dict):
    by_day = {int(r["day"][8:]): r for r in data["days"]}
    t = date.today()
    is_now = data["month"] == t.strftime("%Y-%m")
    cells = "".join(f"<div class='h'>{d}</div>" for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))
    cells += "<div></div>" * data["first_weekday"]
    for n in range(1, data["days_in_month"] + 1):
        r = by_day.get(n)
        cls = "d today" if is_now and n == t.day else "d"
        if r:
            bg, fg = MOOD_COLORS[r["mood"]]
            tip = MOOD_LABELS[r["mood"]] + (f": {r['note']}" if r["note"] else "")
            cells += (f"<div class='{cls} logged' style='background:{bg};color:{fg}' title='{esc(tip)}'>"
                      f"<span class='n'>{n}</span><span class='em'>{MOOD_EMOJI[r['mood']]}</span></div>")
        else:
            cells += f"<div class='{cls}'>{n}</div>"
    md(f"<div class='cal'>{cells}</div>")
    legend = "".join(f"<span><i style='background:{MOOD_COLORS[k][0]}'></i>{MOOD_EMOJI[k]} {MOOD_LABELS[k]}</span>" for k in range(1, 6))
    md(f"<div class='legend'>{legend}</div>")


def mood_summary(data: dict):
    avg = data["average"]
    label = MOOD_LABELS[round(avg)] if avg else "-"
    tiles([("Days logged", data["logged"], "forest", "calendar"),
           ("Average mood", f"{avg} ({label})" if avg else "-", "leaf", "heart")])


def app_shell(user: dict, nav_items: list[tuple], greeting: str = "Welcome back,") -> str:
    """Brand + greeting + log out on top, floating icon navigation at the bottom. Returns the chosen page."""
    inject_css([i for _, i in nav_items])
    with st.container(key="topbar"):
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        with c1:
            md(f"<div class='brandrow'><span class='logo'>{icon('leaf')}</span>SERENX</div>"
               f"<div class='top'>{avatar(user['name'], 52)}<div><div class='hi'>{esc(greeting)}</div>"
               f"<b>{esc(user['name'])}</b></div></div>")
        with c2:
            if st.button("Log out", key="logout"):
                logout()
    with st.container(key="navbar"):
        return st.radio("Menu", [n for n, _ in nav_items], key="nav", horizontal=True, label_visibility="collapsed")


def logout():
    st.session_state.clear()
    st.rerun()


# ================================================================== LOGIN / REGISTER
def auth_page():
    inject_css()
    left, right = st.columns([5, 6], gap="large")

    with left:
        md(f"""<div class='authhero'>
        <span class='logo'>{icon('leaf')}</span>
        <div class='word'>SERENX</div>
        <h1>{esc(TAGLINE)}</h1>
        <p>{esc(SUBLINE)}</p>
        <div class='feat'>{chip('clipboard', 'leaf')}Short daily check-ins from your doctor</div>
        <div class='feat'>{chip('flame', 'leaf')}Streaks and badges that keep you going</div>
        <div class='feat'>{chip('sparkle', 'leaf')}AI-written questions and summaries</div>
        </div>""")

    with right:
        tab_login, tab_pat, tab_doc = st.tabs(["Log in", "Register as patient", "Register as doctor"])

        with tab_login:
            with st.form("login"):
                email = st.text_input("Email")
                pw = st.text_input("Password", type="password")
                if st.form_submit_button("Log in", type="primary"):
                    try:
                        res = api("POST", "/login", json={"email": email, "password": pw})
                        st.session_state.token, st.session_state.user = res["token"], res["user"]
                        st.rerun()
                    except ApiError as e:
                        st.error(str(e))

        with tab_pat:
            doctors = get("/doctors")
            if not doctors:
                st.warning("No doctors are available yet. A doctor needs to register first.")
            else:
                section("Step 1. Choose your doctor")
                labels = {d["id"]: f"{d['name']}  -  {d['specialization'] or 'General'}" for d in doctors}
                chosen = st.radio("Available doctors", list(labels), format_func=labels.get,
                                  index=None, key="reg_doc", label_visibility="collapsed")
                if chosen:
                    bio = next(d["bio"] for d in doctors if d["id"] == chosen)
                    if bio:
                        st.caption(bio)
                section("Step 2. Create your profile")
                with st.form("reg_patient"):
                    name = st.text_input("Full name")
                    age = st.number_input("Age", 1, 120, 25)
                    email = st.text_input("Email", key="rp_email")
                    pw = st.text_input("Password (min 6 characters)", type="password", key="rp_pw")
                    if st.form_submit_button("Create patient account", type="primary"):
                        if not chosen:
                            st.error("Please choose a doctor first.")
                        else:
                            try:
                                res = api("POST", "/register", json={
                                    "role": "patient", "name": name, "email": email, "password": pw,
                                    "age": int(age), "doctor_id": chosen})
                                st.session_state.token, st.session_state.user = res["token"], res["user"]
                                st.session_state.just_registered = True
                                st.rerun()
                            except ApiError as e:
                                st.error(str(e))

        with tab_doc:
            with st.form("reg_doctor"):
                name = st.text_input("Full name (e.g. Dr. Asha Verma)")
                spec = st.text_input("Specialization", placeholder="Clinical Psychologist")
                bio = st.text_area("Short professional bio")
                email = st.text_input("Email", key="rd_email")
                pw = st.text_input("Password (min 6 characters)", type="password", key="rd_pw")
                if st.form_submit_button("Create doctor account", type="primary"):
                    try:
                        res = api("POST", "/register", json={
                            "role": "doctor", "name": name, "email": email, "password": pw,
                            "specialization": spec, "bio": bio})
                        st.session_state.token, st.session_state.user = res["token"], res["user"]
                        st.rerun()
                    except ApiError as e:
                        st.error(str(e))

        section("Demo accounts", "dummy data only")
        for who, mail, pw in (("Doctor", "dr.meera@demo.com", "Doctor@123"),
                              ("Patient, doing well", "riya@demo.com", "Patient@123"),
                              ("Patient, needs attention", "kabir@demo.com", "Patient@123")):
            md(f"<div class='demo'>{avatar('Meera Shah' if who == 'Doctor' else who.replace('Patient, ', ''), 36)}"
               f"<div><b>{esc(who)}</b><span class='m'>{esc(mail)}  /  {esc(pw)}</span></div></div>")


# ================================================================== DOCTOR
DOCTOR_NAV = [("Overview", "home"), ("Patients", "users"), ("Assessments", "clipboard"),
              ("Goals", "target"), ("Assign", "send")]


def doctor_app(user: dict):
    page = app_shell(user, DOCTOR_NAV, "Welcome back,")
    {"Overview": doctor_overview, "Patients": doctor_patients, "Assessments": doctor_assessments,
     "Goals": doctor_goals, "Assign": doctor_assign}[page]()


def review_button(sub: dict, key: str):
    if sub["flagged"] and not sub["reviewed"]:
        if st.button("Mark as reviewed", key=key):
            if post(f"/submissions/{sub['id']}/review"):
                st.rerun()


def submission_expander(s: dict, label: str, key: str):
    flag = "  -  Needs review" if s["flagged"] and not s["reviewed"] else ""
    with st.expander(label + flag):
        if s["flagged"] and not s["reviewed"]:
            md("<span class='flag'>Needs doctor review: a written answer contained worrying words.</span>")
        ai_tag("AI summary")
        st.write(s["summary"])
        st.caption(DISCLAIMER)
        st.markdown("**Original responses**")
        show_answers(s["answers"])
        review_button(s, key)


def doctor_overview():
    user = st.session_state.user
    pts = get("/patients")
    attention = [p for p in pts if p["needs_attention"]]
    on_track = round(100 * (len(pts) - len(attention)) / len(pts)) if pts else None

    progress_card("Patients on track", on_track, f"{len(pts) - len(attention)} of {len(pts)} patients are on track today")
    tiles([("Connected patients", len(pts), "forest", "users"),
           ("Need attention", len(attention), "coral", "alert"),
           ("Flagged responses", sum(p["flagged"] for p in pts), "sun", "shield"),
           ("Pending assessments", sum(p["pending_assessments"] for p in pts), "teal", "clipboard")])
    if attention:
        names = ", ".join(p["name"] for p in attention[:3])
        insight(f"{names} {'needs' if len(attention) == 1 else 'need'} a closer look. Open Patients to review the details.")
    else:
        insight("All your patients are on track today. Nice work.")

    section("Needs attention")
    if not attention:
        md(f"<div class='okbox'>{icon('check')}Everyone is on track.</div>")
    for p in attention:
        reasons = "".join(f"<li>{esc(r)}</li>" for r in p["reasons"])
        md(f"<div class='alert'>{avatar(p['name'], 42)}<div><div class='t'>{esc(p['name'])}</div><ul>{reasons}</ul></div></div>")

    section("Recent submissions")
    subs = get("/submissions?limit=10")
    if not subs:
        empty("No submissions yet. They appear here as soon as a patient completes an assessment.")
    for s in subs:
        submission_expander(s, f"{s['patient_name']} - {s['title']} - {fmt_date(s['submitted_at'])}", f"ov_rev_{s['id']}")


def doctor_patients():
    section("Your patients")
    pts = get("/patients")
    if not pts:
        empty("No patients are connected yet. Patients connect to you when they register and choose you.")
        return
    for p in pts:
        tone, label = ("coral", "Needs attention") if p["needs_attention"] else ("leaf", "On track")
        pct = p["completion_rate"] or 0
        md(f"""<div class='row'>{avatar(p['name'], 48)}<div class='main'>
        <div class='t'>{esc(p['name'])}  {pill(label, tone)}</div>
        <div class='m'>Age {esc(p['age'] or '-')}  |  {p['pending_assessments']} pending  |  {p['open_goals']} open goals  |  {p['missed_7d']} missed this week</div>
        <div class='bar'><i style='width:{pct}%'></i></div></div><div class='end'>{pct}%</div></div>""")

    names = {p["id"]: p["name"] for p in pts}
    pid = st.selectbox("Open a patient profile", list(names), format_func=names.get)
    d = get(f"/patients/{pid}")
    ov, prof = d["overview"], d["profile"]

    tone, label = ("coral", "Needs attention") if ov["needs_attention"] else ("leaf", "On track")
    md(f"""<div class='doccard'>{avatar(prof['name'], 64)}<div><div class='t'>{esc(prof['name'])}  {pill(label, tone)}</div>
    <div class='m'>{esc(prof['email'])}  |  age {esc(prof['age'] or '-')}  |  joined {fmt_date(prof['created_at'])}</div></div></div>""")
    if ov["needs_attention"]:
        st.warning(" | ".join(ov["reasons"]))

    tiles([("Completion", f"{ov['completion_rate']}%" if ov["completion_rate"] is not None else "-", "forest", "trend"),
           ("Missed (7 days)", ov["missed_7d"], "coral", "alert"),
           ("Pending assessments", ov["pending_assessments"], "teal", "clipboard"),
           ("Best streak", max([s["streak"] for s in d["streaks"]], default=0), "sun", "flame")])

    t1, t2, t3, t4 = st.tabs(["Progress", "Assessment responses", "Goal history", "Assigned and upcoming"])

    with t1:
        section("Mood and rating trend")
        trend_chart(d["trend"])
        section("Mood calendar", "logged by the patient")
        pm = month_nav(f"dm{pid}")
        md_ = get(f"/patients/{pid}/mood?month={pm}")
        mood_calendar(md_)
        mood_summary(md_)
        section("AI weekly progress report")
        if st.button("Generate weekly report", key=f"wr_{pid}", type="primary"):
            with st.spinner("Writing report..."):
                res = post(f"/patients/{pid}/weekly-report")
            if res:
                st.session_state[f"report_{pid}"] = res
        res = st.session_state.get(f"report_{pid}")
        if res:
            ai_tag("Weekly report")
            st.write(res["report"])
            st.caption(DISCLAIMER)
        if d["streaks"]:
            section("Streaks")
            for s in d["streaks"]:
                row("flame" if s["kind"] == "goal" else "clipboard", "sun" if s["kind"] == "goal" else "forest",
                    s["title"], s["kind"].title(), end=f"{s['streak']} in a row")

    with t2:
        if not d["submissions"]:
            empty("No assessments submitted yet.")
        for s in d["submissions"]:
            submission_expander(s, f"{s['title']} - due {fmt_date(s['due_date'])} - {FREQ_LABEL[s['frequency']]}",
                                f"pd_rev_{s['id']}")

    with t3:
        if not d["goal_history"]:
            empty("No goal activity yet.")
        else:
            df = pd.DataFrame(d["goal_history"])
            df["Status"] = df["completed"].map({1: "Done", 0: "In progress"})
            df["Date"] = df["due_date"].map(fmt_date)
            st.dataframe(df[["Date", "title", "Status", "progress", "notes"]].rename(
                columns={"title": "Goal", "progress": "Progress %", "notes": "Patient notes"}),
                hide_index=True, width="stretch")

    with t4:
        section("Currently open")
        if not d["pending_assessments"] and not d["current_goals"]:
            empty("Nothing open right now.")
        for x in d["pending_assessments"]:
            row("clipboard", "forest", x["title"], f"due {fmt_date(x['due_date'])}", pill(FREQ_LABEL[x["frequency"]], FREQ_TONE[x["frequency"]]))
        for x in d["current_goals"]:
            row("target", "leaf", x["title"], "", pill(FREQ_LABEL[x["frequency"]], FREQ_TONE[x["frequency"]]),
                "Done" if x["completed"] else f"{x['progress']}%")
        section("Coming up")
        for x in d["upcoming"][:8]:
            row("calendar", "teal", x["title"], fmt_date(x["due_date"]), pill(FREQ_LABEL[x["frequency"]], FREQ_TONE[x["frequency"]]))


# ---- assessments (manual + AI)
def _new_q(text="", qtype="rating", options=None) -> dict:
    return {"id": uuid.uuid4().hex[:8], "text": text, "qtype": qtype, "options": options or []}


TYPE_LABELS = {"rating": "Rating (1-5)", "multiple_choice": "Multiple choice", "text": "Text answer"}


def doctor_assessments():
    section("Assessments")
    tab_new, tab_list = st.tabs(["Create", "My assessments"])

    with tab_new:
        if "draft" not in st.session_state:
            st.session_state.draft = [_new_q()]
        if msg := st.session_state.pop("flash", None):
            st.success(msg)

        md(f"<div class='ainote'>{icon('sparkle')}Generate with AI</div>")
        c1, c2 = st.columns([4, 1])
        topic = c1.text_input("What do you want to understand?",
                              placeholder="Create an assessment to understand a patient's stress and sleep quality",
                              key="ai_topic")
        n = c2.number_input("Questions", 3, 10, 6, key="ai_n")
        if st.button("Generate questions", type="primary"):
            if len(topic.strip()) < 3:
                st.error("Please describe a topic first.")
            else:
                with st.spinner("Thinking..."):
                    res = post("/ai/generate-assessment", {"topic": topic, "n": int(n)})
                if res:
                    st.session_state.draft = [_new_q(q["text"], q["qtype"], q["options"]) for q in res["questions"]]
                    st.session_state["draft_title"] = res["title"]
                    st.session_state["draft_desc"] = res["description"]
                    st.session_state["ai_source"] = res["source"]
                    st.rerun()
        if st.session_state.get("ai_source") == "offline-demo":
            st.caption("Offline demo mode: add an ANTHROPIC_API_KEY to get real AI-written questions.")
        elif st.session_state.get("ai_source") == "claude":
            st.caption("Questions written by AI. Review and edit them before saving.")

        section("Review and edit")
        title = st.text_input("Assessment title", key="draft_title")
        desc = st.text_input("Short description (optional)", key="draft_desc")

        qs = st.session_state.draft
        for i, q in enumerate(list(qs)):
            k = q["id"]
            cols = st.columns([6, 2.2, 1.4])
            q["text"] = cols[0].text_input(f"Question {i + 1}", value=q["text"], key=f"qt_{k}")
            q["qtype"] = cols[1].selectbox("Type", list(TYPE_LABELS), index=list(TYPE_LABELS).index(q["qtype"]),
                                           format_func=TYPE_LABELS.get, key=f"qy_{k}")
            cols[2].markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
            if cols[2].button("Remove", key=f"qd_{k}"):
                qs.remove(q)
                st.rerun()
            if q["qtype"] == "multiple_choice":
                raw = st.text_input("Options (separate with commas)", value=", ".join(q["options"]), key=f"qo_{k}")
                q["options"] = [o.strip() for o in raw.split(",") if o.strip()]

        b1, b2 = st.columns([1, 4])
        if b1.button("Add question"):
            qs.append(_new_q())
            st.rerun()
        if b2.button("Save assessment", type="primary"):
            body = {"title": title, "description": desc,
                    "questions": [{"text": q["text"], "qtype": q["qtype"], "options": q["options"]}
                                  for q in qs if q["text"].strip()]}
            if post("/assessments", body):
                st.session_state.draft = [_new_q()]
                for key in ("draft_title", "draft_desc", "ai_source"):
                    st.session_state.pop(key, None)
                st.session_state.flash = "Assessment saved. Now assign it from the Assign page."
                st.rerun()

    with tab_list:
        items = get("/assessments")
        if not items:
            empty("You have not created any assessments yet.")
        for a in items:
            with st.expander(f"{a['title']} - {len(a['questions'])} questions"):
                if a["description"]:
                    st.caption(a["description"])
                for i, q in enumerate(a["questions"], 1):
                    extra = f"  ({', '.join(q['options'])})" if q["options"] else ""
                    st.write(f"{i}. {q['text']} - *{TYPE_LABELS[q['qtype']]}*{extra}")


def doctor_goals():
    section("Create a goal")
    with st.form("new_goal", clear_on_submit=True):
        title = st.text_input("Goal", placeholder="Practice breathing exercises for 5 minutes")
        desc = st.text_area("Instructions for the patient (optional)")
        if st.form_submit_button("Create goal", type="primary"):
            post("/goals", {"title": title, "description": desc}, "Goal created. Assign it from the Assign page.")
    section("Your goals")
    goals = get("/goals")
    if not goals:
        empty("No goals yet. Create your first one above.")
    for g in goals:
        row("target", "leaf", g["title"], g["description"])


def doctor_assign():
    section("Assign work to patients")
    pts = get("/patients")
    if not pts:
        empty("You need connected patients before you can assign anything.")
        return
    names = {p["id"]: p["name"] for p in pts}
    t1, t2 = st.tabs(["Assign an assessment", "Assign a goal"])

    for tab, kind in ((t1, "assessments"), (t2, "goals")):
        with tab:
            items = get(f"/{kind}")
            if not items:
                empty(f"Create {'an assessment' if kind == 'assessments' else 'a goal'} first.")
                continue
            lookup = {i["id"]: i["title"] for i in items}
            with st.form(f"assign_{kind}"):
                item = st.selectbox("Choose", list(lookup), format_func=lookup.get)
                who = st.multiselect("Patients (one or many)", list(names), format_func=names.get)
                freq = st.selectbox("How often?", list(FREQ_LABEL), index=1, format_func=FREQ_LABEL.get)
                start = st.date_input("Starts on", value=date.today())
                st.caption("Daily, weekly and monthly items appear automatically for the patient on each due date.")
                if st.form_submit_button("Assign", type="primary"):
                    if not who:
                        st.error("Select at least one patient.")
                    else:
                        key = "assessment_id" if kind == "assessments" else "goal_id"
                        post(f"/{kind}/assign", {key: item, "patient_ids": who, "frequency": freq,
                                                 "start_date": start.isoformat()},
                             f"Assigned to {len(who)} patient(s).")


# ================================================================== PATIENT
PATIENT_NAV = [("Home", "home"), ("Assessments", "clipboard"), ("Goals", "target"),
               ("Wellness", "heart"), ("Progress", "trend")]


def patient_app(user: dict):
    page = app_shell(user, PATIENT_NAV, "Welcome back,")
    {"Home": patient_home, "Assessments": patient_assessments,
     "Goals": patient_goals, "Wellness": patient_wellness, "Progress": patient_progress}[page](user)


def patient_home(user: dict):
    if st.session_state.pop("just_registered", False):
        st.success(f"You are now connected to {user['doctor']['name']}. Your doctor can already see you on their dashboard.")
    doc = user.get("doctor") or {}
    a, g, pr = get("/my/assessments"), get("/my/goals"), get("/my/progress")
    open_goals = [x for x in g["current"] if not x["completed"]]
    todo = len(a["pending"]) + len(open_goals)

    if not pr["assigned_total"]:
        md("<div class='empty'>Welcome to SERENX. Your doctor has not assigned any assessments or goals yet. "
           "Your plan, streaks and insights will appear here once they do. Meanwhile, add today's mood in the Wellness tab.</div>")
        rem = get("/my/reminders")
        for x in rem["reminders"]:
            row(x["icon"], x["tone"], x["title"], x["text"])
        md(f"""<div class='doccard'>{avatar(doc.get('name', 'Doctor'), 56)}<div>
        <div class='m'>Your doctor</div><div class='t'>{esc(doc.get('name', '-'))}</div>
        <div class='m'>{esc(doc.get('specialization', ''))}</div></div></div>""")
        return

    progress_card("Completion", pr["completion_rate"],
                  "Share of your assigned tasks completed so far", "trend")
    tiles([("Day streak", pr["best_streak"], "sun", "flame"),
           ("Points", pr["points"], "lime", "star"),
           ("Pending assessments", len(a["pending"]), "forest", "clipboard"),
           ("Goals to do", len(open_goals), "leaf", "target")])

    if pr["best_streak"] >= 7:
        tip = f"You are on a {pr['best_streak']} day streak. Keep it up!"
    elif todo:
        tip = f"{todo} task(s) left today. A short check-in keeps your streak going."
    else:
        tip = "You have finished everything for today. See you tomorrow."
    insight(tip)

    rem = get("/my/reminders")
    if rem["count"]:
        section("Reminders", "worked out when you open the app")
        for x in rem["reminders"]:
            row(x["icon"], x["tone"], x["title"], x["text"])

    section("Today's plan")
    plan = [(x["title"], f"{FREQ_LABEL[x['frequency']]} assessment", False) for x in a["pending"]]
    plan += [(x["title"], "Completed" if x["completed"] else f"{FREQ_LABEL[x['frequency']]} goal, {x['progress']}% done",
              x["completed"]) for x in g["current"]]
    if plan:
        timeline(plan)
        st.caption("Open the Assessments or Goals page to complete these.")
    else:
        empty("Nothing to do today.")

    md(f"""<div class='doccard'>{avatar(doc.get('name', 'Doctor'), 56)}<div>
    <div class='m'>Your doctor</div><div class='t'>{esc(doc.get('name', '-'))}</div>
    <div class='m'>{esc(doc.get('specialization', ''))}</div></div></div>""")

    section("Coming up")
    up = sorted(a["upcoming"] + g["upcoming"], key=lambda x: x["due_date"])[:5]
    if not up:
        empty("Nothing scheduled yet.")
    for x in up:
        row("calendar", "teal", x["title"], fmt_date(x["due_date"]), pill(FREQ_LABEL[x["frequency"]], FREQ_TONE[x["frequency"]]))

    section("Your badges")
    badge_grid(pr["badges"])


def patient_assessments(user: dict):
    section("Assessments")
    tab_p, tab_h = st.tabs(["Pending", "Submitted"])
    with tab_p:
        data = get("/my/assessments")
        if not data["pending"]:
            md(f"<div class='okbox'>{icon('check')}No pending assessments.</div>")
        for p in data["pending"]:
            with st.expander(f"{p['title']} - {FREQ_LABEL[p['frequency']]} - due {fmt_date(p['due_date'])}", expanded=True):
                if p["description"]:
                    st.caption(p["description"])
                with st.form(f"form_{p['assign_id']}_{p['due_date']}"):
                    answers = {}
                    for q in p["questions"]:
                        key = f"ans_{p['assign_id']}_{p['due_date']}_{q['id']}"
                        if q["qtype"] == "rating":
                            answers[str(q["id"])] = st.slider(q["text"], 1, 5, 3, key=key)
                        elif q["qtype"] == "multiple_choice":
                            answers[str(q["id"])] = st.radio(q["text"], q["options"], index=None, key=key)
                        else:
                            answers[str(q["id"])] = st.text_area(q["text"], key=key)
                    if st.form_submit_button("Submit", type="primary"):
                        missing = [q["text"] for q in p["questions"]
                                   if q["qtype"] == "multiple_choice" and not answers[str(q["id"])]]
                        if missing:
                            st.error("Please answer all multiple-choice questions.")
                        else:
                            body = {"assign_id": p["assign_id"], "due_date": p["due_date"],
                                    "answers": {k: (v if v is not None else "") for k, v in answers.items()}}
                            if post("/my/assessments/submit", body):
                                st.success("Submitted. Thank you!")
                                time.sleep(0.8)
                                st.rerun()
        if data["upcoming"]:
            section("Coming up")
            for x in data["upcoming"][:6]:
                row("calendar", "teal", x["title"], fmt_date(x["due_date"]), pill(FREQ_LABEL[x["frequency"]], FREQ_TONE[x["frequency"]]))
    with tab_h:
        hist = get("/my/assessments/history")
        if not hist:
            empty("Nothing submitted yet.")
        for s in hist:
            with st.expander(f"{s['title']} - {fmt_date(s['due_date'])}"):
                show_answers(s["answers"])


def patient_goals(user: dict):
    section("Goals")
    tab_c, tab_h = st.tabs(["My goals", "History"])
    with tab_c:
        data = get("/my/goals")
        if not data["current"]:
            empty("Your doctor has not assigned any goals yet.")
        for g in data["current"]:
            k = f"{g['assign_id']}_{g['due_date']}"
            status = "Completed" if g["completed"] else f"{g['progress']}%"
            with st.expander(f"{g['title']} - {FREQ_LABEL[g['frequency']]} - {status}", expanded=not g["completed"]):
                if g["description"]:
                    st.caption(g["description"])
                with st.form(f"goal_{k}"):
                    progress = st.slider("Progress", 0, 100, int(g["progress"]), step=5, key=f"pg_{k}")
                    done = st.checkbox("Mark as completed", value=g["completed"], key=f"dn_{k}")
                    notes = st.text_area("Notes or reflections", value=g["notes"], key=f"nt_{k}")
                    if st.form_submit_button("Save", type="primary"):
                        if post("/my/goals/update", {"assign_id": g["assign_id"], "due_date": g["due_date"],
                                                     "progress": progress, "completed": done, "notes": notes},
                                "Saved!"):
                            time.sleep(0.6)
                            st.rerun()
        if data["upcoming"]:
            section("Coming up")
            for x in data["upcoming"][:6]:
                row("calendar", "teal", x["title"], fmt_date(x["due_date"]), pill(FREQ_LABEL[x["frequency"]], FREQ_TONE[x["frequency"]]))
    with tab_h:
        hist = get("/my/goals/history")
        if not hist:
            empty("No history yet.")
        else:
            df = pd.DataFrame(hist)
            df["Status"] = df["completed"].map({1: "Done", 0: "In progress"})
            df["Date"] = df["due_date"].map(fmt_date)
            st.dataframe(df[["Date", "title", "Status", "progress", "notes"]].rename(
                columns={"title": "Goal", "progress": "Progress %", "notes": "My notes"}),
                hide_index=True, width="stretch")


def patient_wellness(user: dict):
    section("Wellness", "mood, journal and companion")
    t_mood, t_jour, t_chat = st.tabs(["Mood calendar", "Voice journal", "AI companion"])
    with t_mood:
        wellness_mood()
    with t_jour:
        wellness_journal()
    with t_chat:
        wellness_companion()


def wellness_mood():
    today_mood = get("/my/mood")["today"]
    saved_mood = today_mood["mood"] if today_mood else None
    saved_note = (today_mood or {}).get("note", "")
    st.write("How are you feeling today? Tap an emoji and it is added to your calendar.")
    pick = st.segmented_control("Mood", options=[1, 2, 3, 4, 5], format_func=lambda k: MOOD_EMOJI[k],
                                default=saved_mood, key="mood_pick", label_visibility="collapsed")
    st.caption("   ".join(f"{MOOD_EMOJI[k]} {MOOD_LABELS[k]}" for k in range(1, 6)))
    note = st.text_input("Add a short note (optional, press Enter to save it)", key="mood_note",
                         max_chars=300, value=saved_note)
    if pick and (pick != saved_mood or note != saved_note):
        res = post("/my/mood", {"mood": pick, "note": note})
        if res:
            st.success(f"Added to your calendar: {MOOD_EMOJI[pick]} {MOOD_LABELS[pick]}")
            if res["crisis"]:
                crisis_box(res["help"])
    month = month_nav("pm")
    data = get(f"/my/mood?month={month}")
    mood_calendar(data)
    mood_summary(data)
    st.caption("Hover a coloured day to read your note. Your doctor can see your mood calendar.")


def wellness_journal():
    st.caption("Speak or type. Your entries are private: your doctor cannot see them.")
    if res := st.session_state.pop("journal_result", None):
        if res["crisis"]:
            crisis_box(res["reflection"])
        else:
            ai_tag("Reflection")
            st.write(res["reflection"])
            st.caption(COMPANION_NOTE)
    if speech_to_text is not None:
        langs = {"English (India)": "en-IN", "Hindi": "hi-IN", "Gujarati": "gu-IN"}
        lang = st.selectbox("Speaking language", list(langs), key="jr_lang")
        heard = speech_to_text(start_prompt="Start speaking", stop_prompt="Stop", language=langs[lang],
                               just_once=True, key="jr_voice")
        if heard:
            st.session_state["jr_text"] = (st.session_state.get("jr_text", "") + " " + heard).strip()
            st.session_state["jr_src"] = "voice"
        st.caption("Voice uses your browser's speech recognition (works best in Chrome or Edge). "
                   "You can edit the text before saving.")
    text = st.text_area("Your journal entry", key="jr_text", height=140,
                        placeholder="How was your day? What is on your mind?")
    if st.button("Save entry and get a reflection", type="primary", key="jr_save"):
        if len(text.strip()) < 3:
            st.error("Write or say something first.")
        else:
            with st.spinner("Reading your entry..."):
                res = post("/my/journal", {"text": text, "source": st.session_state.get("jr_src", "typed")})
            if res:
                st.session_state["journal_result"] = res
                st.session_state["jr_src"] = "typed"
                st.session_state.pop("jr_text", None)
                st.rerun()
    section("Past entries")
    entries = get("/my/journal")
    if not entries:
        empty("No entries yet.")
    for e in entries:
        kind = "Voice" if e["source"] == "voice" else "Typed"
        with st.expander(f"{fmt_date(e['created_at'])}  |  {kind}"):
            st.write(e["text"])
            if e["reflection"] and not e["flagged"]:
                ai_tag("Reflection")
                st.write(e["reflection"])
            if st.button("Delete this entry", key=f"jr_del_{e['id']}"):
                api("DELETE", f"/my/journal/{e['id']}")
                st.rerun()


def wellness_companion():
    st.caption(COMPANION_NOTE)
    hist = get("/my/companion")
    if hist["messages"]:
        bubbles = "".join(
            f"<div class='b {'u' if m['role'] == 'user' else ('a c' if '14416' in m['content'] else 'a')}'>{esc(m['content'])}</div>"
            for m in hist["messages"])
        md(f"<div class='chat'>{bubbles}</div>")
    else:
        empty("Say hello. Tell the companion how your day is going.")
    quick = st.session_state.pop("chat_quick", None)
    with st.form("chat_form", clear_on_submit=True):
        msg = st.text_input("Message", key="chat_in", placeholder="Type how you feel...", label_visibility="collapsed")
        sent = st.form_submit_button("Send", type="primary")
    cols = st.columns(3)
    for col, q in zip(cols, ["I feel stressed", "I cannot sleep", "I need motivation"]):
        if col.button(q, key=f"quick_{q}", width="stretch"):
            st.session_state["chat_quick"] = q
            st.rerun()
    text = quick or (msg if sent and msg.strip() else None)
    if text:
        with st.spinner("Thinking..."):
            res = post("/my/companion", {"message": text})
        if res:
            st.rerun()
    if hist["messages"] and st.button("Clear conversation", key="chat_clear"):
        api("DELETE", "/my/companion")
        st.rerun()


def patient_progress(user: dict):
    pr = get("/my/progress")
    tiles([("Points", pr["points"], "lime", "star"),
           ("Best streak", f"{pr['best_streak']} days", "sun", "flame"),
           ("Completion", f"{pr['completion_rate']}%", "leaf", "check")])
    section("Mood trend")
    trend_chart(pr["trend"])
    section("Streaks")
    if not pr["streaks"]:
        empty("Complete your first task to start a streak.")
    for s in pr["streaks"]:
        row("flame" if s["kind"] == "goal" else "clipboard", "sun" if s["streak"] >= 3 else "forest",
            s["title"], s["kind"].title(), end=f"{s['streak']} in a row")
    section("Badges", "grey badges are still locked")
    badge_grid(pr["badges"])


# ================================================================== ROUTER
user = st.session_state.get("user")
if not user or not st.session_state.get("token"):
    auth_page()
elif user["role"] == "doctor":
    doctor_app(user)
else:
    patient_app(user)
