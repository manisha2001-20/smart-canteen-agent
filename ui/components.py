"""Design system: CSS, status badges, token ticket, timeline, stat tiles, empty states.

Everything visual lives here so the page modules stay focused on data + layout.
Cards are keyed Streamlit containers (`st.container(key="mcard_3")`); Streamlit
gives each one a `st-key-<key>` class that the CSS below targets.
"""
import html

import streamlit as st

from utils.helpers import format_currency, format_time, now, parse_ts

# Chart colors (validated: lightness band, CVD separation, contrast on light surface)
CHART_EMERALD = "#047857"
CHART_AMBER = "#d97706"

# status -> (text color, soft background, icon)
STATUS_STYLE = {
    "PENDING":   ("#475569", "#f1f5f9", "⏳"),
    "CONFIRMED": ("#0f766e", "#ccfbf1", "🎫"),
    "PREPARING": ("#b45309", "#fef3c7", "👨‍🍳"),
    "READY":     ("#047857", "#d1fae5", "✅"),
    "COLLECTED": ("#334155", "#e2e8f0", "🍽️"),
    "CANCELLED": ("#be123c", "#ffe4e6", "✖"),
}
PROGRESS_STEPS = [
    ("CONFIRMED", "Confirmed", "confirmed_at", "🎫"),
    ("PREPARING", "Preparing", "preparing_at", "👨‍🍳"),
    ("READY", "Ready", "ready_at", "✅"),
    ("COLLECTED", "Collected", "collected_at", "🍽️"),
]

# Purely decorative thumbnails for menu cards (matched on item name, then category)
ITEM_EMOJI = [
    ("masala dosa", "🥞"), ("set dosa", "🥞"), ("dosa", "🫓"), ("idli", "🍚"), ("pulao", "🍛"),
    ("meals", "🍱"), ("roll", "🌯"), ("sandwich", "🥪"), ("samosa", "🥟"), ("gobi", "🥦"),
    ("coffee", "☕"), ("tea", "🍵"), ("lime", "🍋"), ("badam", "🥛"), ("milk", "🥛"),
]
CATEGORY_STYLE = {
    "South Indian": ("🍛", "linear-gradient(135deg,#fef3c7,#fde68a)"),
    "Meals": ("🍱", "linear-gradient(135deg,#ffedd5,#fed7aa)"),
    "Snacks": ("🥟", "linear-gradient(135deg,#fef9c3,#fde68a)"),
    "Beverages": ("☕", "linear-gradient(135deg,#d1fae5,#a7f3d0)"),
}

CSS = """
<style>
:root {
  --em-900:#053d30; --em-800:#065f46; --em-700:#047857; --em-600:#059669; --em-500:#10b981;
  --em-100:#d1fae5; --em-50:#ecfdf5;
  --am-700:#b45309; --am-600:#d97706; --am-500:#f59e0b; --am-400:#fbbf24; --am-100:#fef3c7; --am-50:#fffbeb;
  --ink:#0f172a; --ink-2:#334155; --muted:#64748b; --line:#e3e8e5; --card:#ffffff; --bg:#f5f7f6;
  --shadow-sm:0 1px 2px rgba(15,23,42,.05);
  --shadow:0 1px 2px rgba(15,23,42,.04), 0 8px 24px -12px rgba(15,23,42,.12);
  --shadow-lg:0 2px 4px rgba(15,23,42,.04), 0 18px 40px -18px rgba(4,120,87,.35);
  --r:16px;
}
/* ---------- app shell ---------- */
[data-testid="stHeader"] {background: transparent;}
[data-testid="stMainBlockContainer"], .block-container {padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1320px;}
h1, h2, h3, h4 {letter-spacing: -.02em; color: var(--ink);}
[data-testid="stCaptionContainer"] {color: var(--muted);}
hr {margin: 1.4rem 0 !important; border-color: var(--line) !important;}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {background: linear-gradient(180deg,#053d30 0%,#064e3b 55%,#065f46 100%);}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top: .6rem;}
.sb-brand {display:flex; align-items:center; gap:.75rem; padding:.2rem 0 .9rem 0;}
.sb-logo {width:44px; height:44px; border-radius:13px; display:grid; place-items:center; font-size:1.45rem;
          background: linear-gradient(135deg,var(--am-400),var(--am-600)); box-shadow:0 6px 16px -6px rgba(251,191,36,.7);}
.sb-name {font-family:"Plus Jakarta Sans",sans-serif; font-weight:800; font-size:1.08rem; color:#fff; line-height:1.15;}
.sb-sub {font-size:.72rem; color:#a7d8c6; letter-spacing:.04em;}
.sb-user {display:flex; align-items:center; gap:.65rem; padding:.7rem .75rem; border-radius:14px;
          background: rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.10); margin-bottom:.5rem;}
.sb-avatar {width:36px; height:36px; border-radius:50%; display:grid; place-items:center; font-weight:700;
            background:#d1fae5; color:#065f46; font-size:.9rem; flex-shrink:0;}
.sb-uname {color:#fff; font-weight:600; font-size:.9rem; line-height:1.2;}
.sb-usn {color:#a7d8c6; font-size:.74rem; font-family:ui-monospace,monospace;}
.sb-label {font-size:.68rem; letter-spacing:.14em; text-transform:uppercase; color:#7fbfa8; font-weight:700; margin:.35rem 0 .35rem .2rem;}
.sb-notif {display:flex; align-items:center; gap:.5rem; font-size:.82rem; color:#e7f5ef; padding:.45rem .7rem;
           border-radius:10px; background:rgba(251,191,36,.14); border:1px solid rgba(251,191,36,.35);}
.sb-notif.none {background:rgba(255,255,255,.05); border-color:rgba(255,255,255,.08); color:#a7d8c6;}
.sb-notif b {color:#fbbf24;}
.sb-status {display:flex; flex-direction:column; gap:.35rem; font-size:.76rem; color:#bfe3d5;}
.sb-status div {display:flex; justify-content:space-between; align-items:center; gap:.6rem; padding:.4rem .6rem; border-radius:8px; background:rgba(255,255,255,.05);}
.sb-status span:first-child {white-space:nowrap;}
.sb-status span:last-child {color:#fff; font-weight:600; text-align:right;}
/* nav radio -> menu list */
/* Streamlit 1.66 radio DOM: radiogroup > div[data-selected] > label[stRadioOption] > div > (circle, markdown) */
[data-testid="stSidebar"] [data-testid="stRadio"], [data-testid="stSidebar"] [data-testid="stRadio"] > div {width: 100%;}
[data-testid="stSidebar"] [role="radiogroup"] {gap: 3px; width: 100%;}
[data-testid="stSidebar"] [role="radiogroup"] > div > label {width: 100%; box-sizing: border-box;}
[data-testid="stButtonGroup"] > div {flex-wrap: wrap; row-gap: 6px;}
[data-testid="stSidebar"] [role="radiogroup"] > div {position: relative; width: 100%;}
[data-testid="stSidebar"] [data-testid="stRadioOption"] {
  width: 100%; margin: 0; padding: .6rem .8rem; border-radius: 11px; cursor: pointer; transition: background .15s ease;}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {background: rgba(255,255,255,.08);}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) {display: none;}
[data-testid="stSidebar"] [data-testid="stRadioOption"] p {font-size: .93rem; font-weight: 500; color: #d7eee5;}
[data-testid="stSidebar"] [role="radiogroup"] > div[data-selected="true"] [data-testid="stRadioOption"] {
  background: #ffffff; box-shadow: 0 6px 18px -8px rgba(0,0,0,.45);}
[data-testid="stSidebar"] [role="radiogroup"] > div[data-selected="true"] p {color: var(--em-800); font-weight: 700;}
[data-testid="stSidebar"] [role="radiogroup"] > div:nth-child(4) {margin-top: 2.1rem;}
[data-testid="stSidebar"] [role="radiogroup"] > div:nth-child(4)::before {
  content: "CANTEEN STAFF"; position: absolute; top: -1.55rem; left: .2rem; font-size: .68rem; letter-spacing: .14em;
  color: #7fbfa8; font-weight: 700;}
[data-testid="stSidebar"] .stButton button {background: transparent; border:1px solid rgba(255,255,255,.22); color:#e7f5ef;}
[data-testid="stSidebar"] .stButton button:hover {border-color:#fbbf24; color:#fbbf24;}

/* ---------- buttons, tabs, inputs ---------- */
.stButton button, .stFormSubmitButton button {font-weight: 600; transition: transform .08s ease, box-shadow .15s ease;}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(135deg,var(--em-600),var(--em-800)); border: 0; color: #fff;
  box-shadow: 0 6px 16px -8px rgba(4,120,87,.8);}
.stButton button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {transform: translateY(-1px); box-shadow: 0 10px 22px -10px rgba(4,120,87,.9); color:#fff;}
.stButton button:disabled, [data-testid^="stBaseButton"]:disabled {
  background: #eef2f0 !important; color: #9aa8a2 !important; box-shadow: none !important; border: 1px solid var(--line) !important;
  transform: none !important; cursor: not-allowed;}
/* Streamlit 1.66 tabs: [role=tablist] > [data-testid=stTab][aria-selected] (+ an inner underline div) */
[data-testid="stMain"] [role="tablist"] {gap: 6px; background: #e6edea; padding: 5px; border-radius: 14px; width: fit-content;
  max-width: 100%; overflow-x: auto; border: 0; box-shadow: none;}
[data-testid="stMain"] [role="tablist"]::after, [data-testid="stMain"] [role="tablist"]::before {display: none;}
[data-testid="stTab"] {height: auto; padding: .5rem 1.05rem; border-radius: 10px; color: var(--ink-2); border: 0; margin: 0;}
[data-testid="stTab"] p {font-weight: 600; font-size: .92rem;}
[data-testid="stTab"]:hover {background: rgba(255,255,255,.6);}
[data-testid="stTab"][aria-selected="true"] {background: #fff; box-shadow: var(--shadow-sm);}
[data-testid="stTab"][aria-selected="true"] p {color: var(--em-800);}
[data-testid="stTab"] > div:not([data-testid]) {display: none;}
[data-testid="stTabPanel"] {padding-top: 1.1rem;}
[data-testid="stExpander"] details {border-radius: var(--r); background: var(--card); border-color: var(--line);}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {border-radius: 12px; overflow: hidden; border: 1px solid var(--line);}
[data-testid="stForm"] {background: var(--card); border: 1px solid var(--line); border-radius: 20px; padding: 1.5rem; box-shadow: var(--shadow);}
[data-testid="stAlert"] {border-radius: 14px;}

/* ---------- generic card containers ---------- */
[class*="st-key-card_"], [class*="st-key-mcard_"], [class*="st-key-ocard_"], [class*="st-key-kcard_"],
[class*="st-key-ncard_"], .st-key-cartbox, [class*="st-key-chart_"] {
  background: var(--card); border: 1px solid var(--line); border-radius: var(--r); box-shadow: var(--shadow);
  padding: 1.1rem 1.15rem;}

/* ---------- hero ---------- */
.sc-hero {position: relative; overflow: hidden; border-radius: 22px; padding: 1.6rem 1.8rem; margin-bottom: 1.3rem; color: #fff;
  background: radial-gradient(circle at 88% 20%, rgba(251,191,36,.35) 0, transparent 38%),
              linear-gradient(120deg,#053d30 0%,#065f46 45%,#047857 100%);
  box-shadow: var(--shadow-lg);}
.sc-hero::after {content:""; position:absolute; right:-60px; bottom:-90px; width:240px; height:240px; border-radius:50%;
  border: 36px solid rgba(255,255,255,.06);}
.sc-hero .eyebrow {display:inline-flex; align-items:center; gap:.4rem; font-size:.72rem; font-weight:700; letter-spacing:.12em;
  text-transform:uppercase; color:#fde68a; background:rgba(251,191,36,.14); border:1px solid rgba(251,191,36,.35);
  padding:.25rem .65rem; border-radius:999px; margin-bottom:.65rem;}
.sc-hero h1 {color:#fff; font-size:clamp(1.35rem, 2.6vw, 2rem); margin:0; padding:0; line-height:1.2;}
.sc-hero p {margin:.45rem 0 0 0; color:#c8eadc; font-size:.98rem; max-width:720px;}

/* ---------- section titles ---------- */
.sc-section {display:flex; align-items:flex-end; justify-content:space-between; gap:1rem; margin:.4rem 0 .8rem 0;}
.sc-section h3 {margin:0; padding:0; font-size:1.15rem;}
.sc-section p {margin:.15rem 0 0 0; color:var(--muted); font-size:.85rem;}

/* ---------- stat tiles ---------- */
.sc-stats {display:grid; grid-template-columns:repeat(auto-fit, minmax(148px, 1fr)); gap:.75rem; margin:0 0 1.2rem 0;}
.sc-stat {background:var(--card); border:1px solid var(--line); border-radius:var(--r); padding:.95rem 1.05rem; box-shadow:var(--shadow);
  display:flex; gap:.8rem; align-items:center; min-width:0;}
.sc-stat .ic {width:42px; height:42px; border-radius:12px; display:grid; place-items:center; font-size:1.2rem; flex-shrink:0;}
.sc-stat .ic.em {background:var(--em-50); color:var(--em-700);} .sc-stat .ic.am {background:var(--am-50);} .sc-stat .ic.sl {background:#f1f5f9;}
.sc-stat .lb {font-size:.76rem; color:var(--muted); font-weight:500; line-height:1.25;}
.sc-stat {padding:.85rem .9rem; gap:.65rem;} .sc-stat .ic {width:38px; height:38px; font-size:1.05rem;}
.sc-stat .vl {font-family:"Plus Jakarta Sans",sans-serif; font-size:1.4rem; font-weight:800; color:var(--ink); line-height:1.15; white-space:nowrap;}

/* ---------- badges & chips ---------- */
.sc-badge {display:inline-flex; align-items:center; gap:.3rem; padding:.2rem .65rem; border-radius:999px; font-size:.74rem;
  font-weight:700; letter-spacing:.02em; white-space:nowrap;}
.sc-chip {display:inline-flex; align-items:center; gap:.25rem; padding:.15rem .55rem; border-radius:8px; font-size:.74rem;
  background:#f1f5f4; color:var(--ink-2); margin-right:.3rem; font-weight:500;}
.sc-chip.am {background:var(--am-50); color:var(--am-700);}
.sc-muted {color:var(--muted); font-size:.84rem;}
.sc-price {font-family:"Plus Jakarta Sans",sans-serif; font-weight:800; font-size:1.15rem; color:var(--ink);}

/* ---------- menu cards ---------- */
[class*="st-key-mcard_"] {padding:.85rem; transition: transform .15s ease, box-shadow .2s ease; height: 100%;}
[class*="st-key-mcard_"]:hover {transform: translateY(-2px); box-shadow: var(--shadow-lg);}
.mc-thumb {height:96px; border-radius:12px; display:grid; place-items:center; font-size:2.7rem; position:relative; margin-bottom:.7rem;}
.mc-thumb .avail {position:absolute; top:8px; right:8px;}
.mc-thumb .prep {position:absolute; bottom:8px; left:8px; background:rgba(255,255,255,.88); color:var(--ink-2);
  font-size:.72rem; font-weight:600; padding:.15rem .5rem; border-radius:999px;}
.mc-name {font-family:"Plus Jakarta Sans",sans-serif; font-weight:700; font-size:1rem; color:var(--ink); line-height:1.25;}
.mc-desc {color:var(--muted); font-size:.8rem; line-height:1.35; height:2.7em; margin:.2rem 0 .55rem 0;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;}
.mc-name {white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.mc-foot {display:flex; justify-content:space-between; align-items:center; margin-bottom:.35rem;}
.mc-off {filter: grayscale(.85); opacity:.6;}

/* ---------- cart ---------- */
.st-key-cartbox {position: sticky; top: 3.6rem; border-top: 4px solid var(--em-600);}
.cart-head {display:flex; justify-content:space-between; align-items:center; margin-bottom:.6rem;}
.cart-head h3 {margin:0; padding:0; font-size:1.1rem;}
.cart-count {background:var(--em-50); color:var(--em-700); font-weight:700; font-size:.75rem; padding:.15rem .6rem; border-radius:999px;}
.cart-line .nm {font-weight:600; font-size:.9rem; color:var(--ink); line-height:1.25;}
.cart-line .sub {font-size:.78rem; color:var(--muted);}
[class*="st-key-minus_"] button, [class*="st-key-plus_"] button, [class*="st-key-rm_"] button {
  min-height: 2rem; padding: 0 .3rem; border-radius: 9px;}
.cart-sum {border-top:1px dashed var(--line); margin-top:.6rem; padding-top:.7rem;}
.cart-sum .row {display:flex; justify-content:space-between; font-size:.86rem; color:var(--ink-2); padding:.12rem 0;}
.cart-sum .total {font-family:"Plus Jakarta Sans",sans-serif; font-weight:800; font-size:1.35rem; color:var(--ink); padding-top:.35rem;}
.eta-pill {display:flex; gap:.55rem; align-items:center; background:var(--am-50); border:1px solid #fde68a; color:#92400e;
  border-radius:12px; padding:.55rem .75rem; font-size:.84rem; margin:.7rem 0;}
.eta-pill b {color:#78350f;}
.cart-empty {text-align:center; padding:1.4rem .5rem; color:var(--muted);}
.cart-empty .big {font-size:2.4rem;}

/* ---------- token ticket ---------- */
.tk {position:relative; border-radius:24px; overflow:hidden; color:#fff; margin:.4rem 0 1rem 0; box-shadow:var(--shadow-lg);
  background: radial-gradient(circle at 92% 8%, rgba(251,191,36,.38) 0, transparent 35%), linear-gradient(135deg,#053d30,#047857);}
.tk-top {padding:1.6rem 1.8rem 1.3rem 1.8rem; display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; flex-wrap:wrap;}
.tk-eyebrow {font-size:.72rem; letter-spacing:.16em; text-transform:uppercase; color:#a7f3d0; font-weight:700;}
.tk-num {font-family:"Plus Jakarta Sans",sans-serif; font-size:clamp(3.4rem, 9vw, 5.6rem); font-weight:800; line-height:.95;
  letter-spacing:.04em; color:#fff; text-shadow:0 6px 30px rgba(0,0,0,.25); margin-top:.35rem;}
.tk-code {font-family:ui-monospace,monospace; font-size:.82rem; color:#c8eadc; margin-top:.5rem;}
.tk-status {background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.22); border-radius:14px; padding:.6rem .9rem; font-size:.85rem; color:#e7f5ef;}
.tk-status b {color:#fde68a;}
.tk-perf {position:relative; height:0; border-top:2px dashed rgba(255,255,255,.28); margin:0 1.2rem;}
.tk-perf::before, .tk-perf::after {content:""; position:absolute; top:-15px; width:28px; height:28px; border-radius:50%; background:var(--bg);}
.tk-perf::before {left:-2.6rem;} .tk-perf::after {right:-2.6rem;}
.tk-grid {display:grid; grid-template-columns:repeat(4, 1fr); gap:1rem; padding:1.15rem 1.8rem 1.4rem 1.8rem;}
.tk-grid .lbl {font-size:.68rem; text-transform:uppercase; letter-spacing:.12em; color:#a7f3d0; font-weight:600;}
.tk-grid .val {font-family:"Plus Jakarta Sans",sans-serif; font-size:1.3rem; font-weight:800; color:#fff; margin-top:.15rem;}
.tk-grid .val.am {color:#fde68a;}

/* ---------- order timeline ---------- */
.tl {display:flex; align-items:flex-start; margin:.9rem 0 .3rem 0;}
.tl-step {flex:1; display:flex; flex-direction:column; align-items:center; text-align:center; position:relative; min-width:0;}
.tl-step:not(:last-child)::after {content:""; position:absolute; top:17px; left:calc(50% + 20px); right:calc(-50% + 20px); height:3px;
  border-radius:3px; background:#e5ebe8;}
.tl-step.done:not(:last-child)::after {background:var(--em-600);}
.tl-dot {width:36px; height:36px; border-radius:50%; display:grid; place-items:center; font-size:.95rem; background:#f1f5f4;
  border:2px solid #e2e8e5; color:#94a3b8; position:relative; z-index:1;}
.tl-step.done .tl-dot {background:var(--em-600); border-color:var(--em-600); color:#fff;}
.tl-step.now .tl-dot {background:#fff; border:3px solid var(--am-500); box-shadow:0 0 0 6px rgba(245,158,11,.18); animation: tlpulse 1.8s ease-in-out infinite;}
@keyframes tlpulse {50% {box-shadow:0 0 0 10px rgba(245,158,11,.06);}}
.tl-name {font-size:.78rem; font-weight:700; color:#94a3b8; margin-top:.4rem;}
.tl-step.done .tl-name {color:var(--em-800);} .tl-step.now .tl-name {color:var(--am-700);}
.tl-time {font-size:.7rem; color:var(--muted); min-height:1em;}
.tl-cancel {display:flex; gap:.5rem; align-items:center; background:#fff1f2; color:#9f1239; border:1px solid #fecdd3;
  border-radius:12px; padding:.55rem .8rem; font-size:.85rem; margin-top:.7rem;}

/* ---------- live order cards ---------- */
.oc-token {border-radius:16px; padding:.9rem .6rem; text-align:center; background:linear-gradient(135deg,#053d30,#047857); color:#fff;}
.oc-token .lbl {font-size:.62rem; letter-spacing:.16em; color:#a7f3d0; font-weight:700;}
.oc-token .num {font-family:"Plus Jakarta Sans",sans-serif; font-size:2.1rem; font-weight:800; line-height:1.05; letter-spacing:.03em;}
.oc-token.ready {background:linear-gradient(135deg,#b45309,#f59e0b);}
.oc-token.ready .lbl {color:#fef3c7;}
.oc-title {font-weight:700; color:var(--ink); font-size:1rem; margin:.35rem 0 .1rem 0;}
.oc-ready {display:flex; gap:.6rem; align-items:center; background:linear-gradient(90deg,#ecfdf5,#fffbeb); border:1px solid #a7f3d0;
  border-radius:12px; padding:.6rem .8rem; color:#065f46; font-weight:600; font-size:.9rem; margin-top:.6rem;}
.oc-kv {font-size:.7rem; color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-weight:600;}
.oc-val {font-family:"Plus Jakarta Sans",sans-serif; font-weight:800; font-size:1.25rem; color:var(--ink);}

/* ---------- notifications ---------- */
[class*="st-key-ncard_"] {padding:.95rem 1.05rem;}
.nt {display:flex; gap:.9rem; align-items:flex-start;}
.nt-ic {width:42px; height:42px; border-radius:12px; display:grid; place-items:center; font-size:1.15rem; flex-shrink:0;}
.nt-body {flex:1; min-width:0;}
.nt-title {font-weight:700; color:var(--ink); font-size:.95rem; display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;}
.nt-msg {color:var(--ink-2); font-size:.88rem; margin-top:.15rem; line-height:1.45;}
.nt-time {color:var(--muted); font-size:.76rem; white-space:nowrap;}
.nt-new {background:var(--am-500); color:#fff; font-size:.62rem; font-weight:800; letter-spacing:.08em; padding:.1rem .45rem; border-radius:999px;}
.nt.read {opacity:.72;}

/* ---------- kanban ---------- */
.kb-head {display:flex; justify-content:space-between; align-items:center; padding:.7rem .9rem; border-radius:14px; margin-bottom:.7rem; font-weight:700;}
.kb-head .n {background:rgba(255,255,255,.75); border-radius:999px; padding:.05rem .6rem; font-size:.85rem;}
[class*="st-key-kcard_"] {padding:.9rem 1rem; border-left:5px solid var(--kb, var(--em-600));}
[class*="st-key-kcard_CONFIRMED"] {--kb:#0f766e;}
[class*="st-key-kcard_PREPARING"] {--kb:#d97706;}
[class*="st-key-kcard_READY"] {--kb:#047857; background: linear-gradient(180deg,#f0fdf8,#fff 60%);}
.kc-top {display:flex; justify-content:space-between; align-items:baseline; gap:.5rem;}
.kc-token {font-family:"Plus Jakarta Sans",sans-serif; font-size:1.7rem; font-weight:800; color:var(--ink); letter-spacing:.02em;}
.kc-age {font-size:.75rem; color:var(--muted); white-space:nowrap;}
.kc-student {font-weight:600; color:var(--ink-2); font-size:.88rem;}
.kc-items {margin:.45rem 0; padding:.5rem .65rem; background:#f7faf8; border-radius:10px; font-size:.86rem; color:var(--ink); line-height:1.6;}
.kc-items b {color:var(--em-700);}
.kc-note {font-size:.8rem; color:#92400e; background:var(--am-50); border-radius:8px; padding:.3rem .55rem; margin-bottom:.4rem;}
.kc-meta {display:flex; justify-content:space-between; font-size:.78rem; color:var(--muted); margin-bottom:.4rem; gap:.5rem; flex-wrap:wrap;}
.kb-empty {border:2px dashed var(--line); border-radius:14px; padding:1.4rem; text-align:center; color:var(--muted); font-size:.85rem;}

/* ---------- analytics ---------- */
[class*="st-key-chart_"] h4 {font-size:1rem; margin:0 0 .1rem 0; padding:0;}
.st-bars .r {display:grid; grid-template-columns: 130px 1fr 40px; gap:.6rem; align-items:center; margin:.45rem 0; font-size:.84rem;}
.st-bars .track {height:12px; background:#eef2f0; border-radius:4px; overflow:hidden;}
.st-bars .fill {height:100%; border-radius:4px;}
.st-bars .n {text-align:right; font-weight:700; color:var(--ink);}

/* ---------- agent pipeline ---------- */
.ag-flow {display:flex; align-items:stretch; gap:0; padding:.7rem .1rem 1rem .1rem;}
.ag-node {flex:1 1 0; min-width:0; background:var(--card); border:1px solid var(--line); border-radius:16px; padding:.85rem .5rem;
  box-shadow:var(--shadow); text-align:center; position:relative;}
.ag-node.actor {background:var(--am-50); border-color:#fde68a;}
.ag-node.coord {background:linear-gradient(135deg,#053d30,#047857); border:0; color:#fff;}
.ag-node .ic {font-size:1.6rem;}
.ag-node .nm {font-family:"Plus Jakarta Sans",sans-serif; font-weight:800; font-size:.92rem; margin-top:.25rem; color:var(--ink);}
.ag-node.coord .nm {color:#fff;}
.ag-node .rl {font-size:.74rem; color:var(--muted); margin-top:.2rem; line-height:1.35;}
.ag-node.coord .rl {color:#c8eadc;}
.ag-node .step {position:absolute; top:-9px; left:50%; transform:translateX(-50%); background:var(--am-500); color:#fff; font-size:.65rem;
  font-weight:800; border-radius:999px; padding:.05rem .5rem;}
.ag-arrow {flex:0 0 20px; display:grid; place-items:center; color:var(--em-600); font-size:1.1rem; font-weight:800;}
.ag-node.actor {flex-grow:.8;}
.ag-node .nm, .ag-node .rl {overflow-wrap:anywhere;}
.ag-intents code {overflow-wrap:anywhere;}
@media (max-width: 1250px) {
  .ag-flow {flex-direction:column; max-width:520px; margin:0 auto;}
  .ag-arrow {transform:rotate(90deg); flex-basis:28px;}
}
.ag-intents {display:flex; flex-wrap:wrap; gap:.3rem; justify-content:center; margin-top:.5rem;}
.ag-intents code {font-size:.66rem; background:var(--em-50); color:var(--em-800); border-radius:6px; padding:.05rem .35rem;}
.ag-node.coord .ag-intents code {background:rgba(255,255,255,.14); color:#e7f5ef;}
.ag-feed {display:flex; flex-direction:column; gap:.4rem;}
.ag-msg {display:grid; grid-template-columns: 70px 1fr; gap:.7rem; align-items:start; padding:.55rem .75rem; border-radius:12px;
  background:var(--card); border:1px solid var(--line);}
.ag-msg .t {font-family:ui-monospace,monospace; font-size:.74rem; color:var(--muted); padding-top:.1rem;}
.ag-msg .route {font-size:.85rem; color:var(--ink);} .ag-msg .route b {color:var(--em-800);}
.ag-msg .route .x {color:var(--am-600); font-weight:800; margin:0 .25rem;}
.ag-msg .d {font-family:ui-monospace,monospace; font-size:.72rem; color:var(--muted); word-break:break-all; margin-top:.15rem;}
.ag-msg.fail {border-color:#fecdd3; background:#fff1f2;}
.cfg-row {display:flex; flex-wrap:wrap; gap:.5rem; margin:.2rem 0 1rem 0;}
.cfg-row span {background:var(--card); border:1px solid var(--line); border-radius:999px; padding:.3rem .8rem; font-size:.8rem; color:var(--ink-2);}
.cfg-row b {color:var(--em-800);}

/* ---------- login ---------- */
.lg-steps {display:flex; flex-direction:column; gap:.7rem;}
.lg-step {display:flex; gap:.85rem; align-items:flex-start; background:var(--card); border:1px solid var(--line); border-radius:16px; padding:.85rem 1rem; box-shadow:var(--shadow-sm);}
.lg-step .n {width:34px; height:34px; border-radius:10px; display:grid; place-items:center; font-weight:800; background:var(--em-50); color:var(--em-700); flex-shrink:0;}
.lg-step .h {font-weight:700; color:var(--ink); font-size:.93rem;}
.lg-step .s {color:var(--muted); font-size:.82rem;}
.lg-demo {margin-top:.8rem; font-size:.82rem; color:var(--muted);}
.lg-demo code {background:var(--em-50); color:var(--em-800); padding:.05rem .4rem; border-radius:6px;}

/* ---------- empty state ---------- */
.sc-empty {text-align:center; padding:2.2rem 1rem; background:var(--card); border:1px dashed #cfd8d3; border-radius:var(--r);}
.sc-empty .i {font-size:2.4rem;} .sc-empty .h {font-weight:700; color:var(--ink); margin-top:.3rem;} .sc-empty .s {color:var(--muted); font-size:.86rem;}

/* ---------- responsive ---------- */
@media (max-width: 1100px) {
  .tk-grid {grid-template-columns: repeat(2, 1fr);}
  .st-key-cartbox {position: static;}
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"], .block-container {padding-left: 1rem; padding-right: 1rem; padding-top: 1.2rem;}
  .sc-hero {padding: 1.2rem 1.15rem; border-radius: 18px;}
  .tk-top, .tk-grid {padding-left: 1.2rem; padding-right: 1.2rem;}
  .tk-grid .val {font-size: 1.1rem;}
  .tl-name {font-size: .68rem;} .tl-dot {width: 30px; height: 30px; font-size: .8rem;}
  .tl-step:not(:last-child)::after {top: 14px;}
  .ag-flow {flex-direction: column;} .ag-arrow {transform: rotate(90deg); flex-basis: 26px;}
  .st-bars .r {grid-template-columns: 95px 1fr 32px;}
  .sc-stats {grid-template-columns: repeat(2, minmax(0, 1fr));}
  .sc-stat .vl {font-size: 1.15rem;}
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def hero(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    eb = f"<div class='eyebrow'>{esc(eyebrow)}</div>" if eyebrow else ""
    st.markdown(f"<div class='sc-hero'>{eb}<h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>", unsafe_allow_html=True)


def section(title: str, subtitle: str = "", right_html: str = "") -> None:
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    st.markdown(f"<div class='sc-section'><div><h3>{esc(title)}</h3>{sub}</div>{right_html}</div>", unsafe_allow_html=True)


def stat_tiles(tiles: list[tuple]) -> None:
    """tiles: (icon, label, value, tone) with tone in em | am | sl."""
    cells = "".join(
        f"<div class='sc-stat'><div class='ic {tone}'>{icon}</div><div style='min-width:0'>"
        f"<div class='lb'>{esc(label)}</div><div class='vl'>{esc(value)}</div></div></div>"
        for icon, label, value, tone in tiles
    )
    st.markdown(f"<div class='sc-stats'>{cells}</div>", unsafe_allow_html=True)


def empty_state(icon: str, title: str, text: str = "") -> None:
    st.markdown(f"<div class='sc-empty'><div class='i'>{icon}</div><div class='h'>{esc(title)}</div>"
                f"<div class='s'>{esc(text)}</div></div>", unsafe_allow_html=True)


def status_badge(status: str) -> str:
    color, bg, icon = STATUS_STYLE.get(status, ("#475569", "#f1f5f9", "•"))
    return f"<span class='sc-badge' style='color:{color};background:{bg}'>{icon} {status.title()}</span>"


def item_emoji(name: str, category: str) -> tuple[str, str]:
    lowered = name.lower()
    cat_icon, gradient = CATEGORY_STYLE.get(category, ("🍽️", "linear-gradient(135deg,#ecfdf5,#d1fae5)"))
    for needle, icon in ITEM_EMOJI:
        if needle in lowered:
            return icon, gradient
    return cat_icon, gradient


def timeline(order: dict) -> str:
    """Horizontal tracker built from the order's own status timestamps."""
    status = order["status"]
    if status == "CANCELLED":
        reason = esc(order.get("cancel_reason") or "No reason given")
        return (f"<div class='tl-cancel'>✖ <div><b>Cancelled</b> at {format_time(order.get('cancelled_at'))}"
                f" · {reason}</div></div>")
    keys = [s[0] for s in PROGRESS_STEPS]
    current = keys.index(status) if status in keys else -1
    cells = []
    for i, (key, label, ts_col, icon) in enumerate(PROGRESS_STEPS):
        if i < current or (i == current and key == "COLLECTED"):
            css, dot = "done", "✓"
        elif i == current:
            css, dot = "now", icon
        else:
            css, dot = "", str(i + 1)
        ts = order.get(ts_col)
        cells.append(f"<div class='tl-step {css}'><div class='tl-dot'>{dot}</div>"
                     f"<div class='tl-name'>{label}</div><div class='tl-time'>{format_time(ts) if ts else '&nbsp;'}</div></div>")
    return f"<div class='tl'>{''.join(cells)}</div>"


# kept for backwards compatibility with older page code
progress_tracker = timeline


def minutes_left(order: dict) -> int | None:
    ready_at = parse_ts(order.get("estimated_ready_at"))
    if not ready_at:
        return None
    return max(0, round((ready_at - now()).total_seconds() / 60))


def eta_text(order: dict) -> str:
    status = order["status"]
    if status == "READY":
        return "Ready now - collect at the counter"
    if status in ("COLLECTED", "CANCELLED"):
        return "-"
    left = minutes_left(order)
    if left is None:
        return "Estimating..."
    if left == 0:
        return "Any moment now"
    return f"~{left} min (by {format_time(order['estimated_ready_at'])})"


def token_card(result: dict) -> None:
    st.markdown(
        f"""<div class='tk'>
          <div class='tk-top'>
            <div>
              <div class='tk-eyebrow'>Your digital token · show at the counter</div>
              <div class='tk-num'>{esc(result['token_number'])}</div>
              <div class='tk-code'>{esc(result['order_code'])}</div>
            </div>
            <div class='tk-status'>Status: <b>{esc(result.get('status', 'CONFIRMED')).title()}</b><br>
              We'll notify you when it's ready 🔔</div>
          </div>
          <div class='tk-perf'></div>
          <div class='tk-grid'>
            <div><div class='lbl'>Estimated ready time</div><div class='val am'>{result['wait_minutes']} minutes</div></div>
            <div><div class='lbl'>Ready by</div><div class='val'>{format_time(result['ready_at'])}</div></div>
            <div><div class='lbl'>Queue position</div><div class='val'>#{result['queue_position']}</div></div>
            <div><div class='lbl'>Order total</div><div class='val'>{format_currency(result['total'])}</div></div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def agent_trace(trace: list[dict]) -> None:
    rows = []
    for step in trace:
        css = "" if step["success"] else " fail"
        mark = "✓" if step["success"] else "✖"
        rows.append(
            f"<div class='ag-msg{css}'><div class='t'>{esc(step['at'][11:])}</div><div>"
            f"<div class='route'>{mark} <b>CoordinatorAgent</b><span class='x'>→</span><b>{esc(step['agent'])}</b>"
            f" &nbsp;<span class='sc-chip'>{esc(step['intent'])}</span></div>"
            f"<div class='d'>{esc(step['detail'])}</div></div></div>"
        )
    st.markdown(f"<div class='ag-feed'>{''.join(rows)}</div>", unsafe_allow_html=True)
