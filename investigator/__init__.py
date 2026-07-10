import json
from pathlib import Path

import httpx
import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PipelineDoc · AI Failure Diagnosis",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Service URLs ──────────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

LOG_COLLECTOR = os.getenv("LOG_COLLECTOR_URL",  "http://localhost:8001")
DIAGNOSIS     = os.getenv("DIAGNOSIS_URL",       "http://localhost:8002")
OWNERSHIP     = os.getenv("OWNERSHIP_URL",       "http://localhost:8003")
NOTIFICATION  = os.getenv("NOTIFICATION_URL",    "http://localhost:8004")
TIMEOUT       = httpx.Timeout(120.0)

# ── Sample payloads ───────────────────────────────────────────────────────────
_SAMPLES_DIR = Path(__file__).parent.parent / "demo" / "sample_logs"

SAMPLES = {
    "dbt": json.loads((_SAMPLES_DIR / "dbt_failure.json").read_text()),
    "airflow": json.loads((_SAMPLES_DIR / "airflow_failure.json").read_text()),
    "fivetran": json.loads((_SAMPLES_DIR / "fivetran_failure.json").read_text()),
}

TOOL_ICONS = {"dbt": "⚙️", "airflow": "🌬️", "fivetran": "🔗"}

SEVERITY_CONFIG = {
    "high":   {"color": "#FF4B4B", "bg": "#FFF0F0", "emoji": "🔴", "label": "HIGH"},
    "medium": {"color": "#FFA500", "bg": "#FFF8E7", "emoji": "🟡", "label": "MEDIUM"},
    "low":    {"color": "#21C55D", "bg": "#F0FFF4", "emoji": "🟢", "label": "LOW"},
}

CONFIDENCE_CONFIG = {
    "high":   {"emoji": "✅", "label": "High"},
    "medium": {"emoji": "❓", "label": "Medium"},
    "low":    {"emoji": "⚠️", "label": "Low"},
}

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Global font */
html, body, [class*="css"] { font-family: "Inter", sans-serif; }

/* Hide default Streamlit menu & footer */
#MainMenu, footer { visibility: hidden; }

/* Header bar */
.header-bar {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}
.header-title {
    font-size: 2rem;
    font-weight: 800;
    color: #fff;
    margin: 0;
    letter-spacing: -0.5px;
}
.header-subtitle {
    font-size: 0.95rem;
    color: #94a3b8;
    margin: 0;
}

/* Pipeline stage strip */
.pipeline-strip {
    display: flex;
    gap: 0;
    margin: 1.2rem 0;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}
.stage-box {
    flex: 1;
    padding: 0.8rem 1rem;
    text-align: center;
    font-size: 0.78rem;
    font-weight: 600;
    background: #f8fafc;
    color: #94a3b8;
    border-right: 1px solid #e2e8f0;
    transition: all 0.3s;
}
.stage-box:last-child { border-right: none; }
.stage-box.active   { background: #eff6ff; color: #2563eb; }
.stage-box.done     { background: #f0fdf4; color: #16a34a; }
.stage-box.error    { background: #fff0f0; color: #dc2626; }
.stage-num {
    display: block;
    font-size: 1.1rem;
    margin-bottom: 2px;
}

/* Result card */
.result-card {
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    border-left: 5px solid;
}
.section-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 0.35rem;
}
.section-value {
    font-size: 1rem;
    color: #1e293b;
    line-height: 1.6;
    white-space: pre-wrap;
}
.meta-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 1.2rem;
}
.meta-item {
    background: rgba(0,0,0,0.03);
    border-radius: 8px;
    padding: 0.7rem 1rem;
}

/* Slack preview card */
.slack-preview {
    background: #1a1d21;
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    font-family: "Slack-Lato", "Lato", sans-serif;
    color: #d1d2d3;
    font-size: 0.88rem;
    line-height: 1.6;
    border-left: 4px solid;
}
.slack-header {
    font-size: 1rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 0.5rem;
}
.slack-field-label { color: #9b9c9e; font-size: 0.78rem; font-weight: 700; }
.slack-field-value { color: #d1d2d3; }
.slack-section-title { color: #ffffff; font-weight: 700; margin-top: 0.8rem; }
.slack-footer { color: #616061; font-size: 0.75rem; margin-top: 0.8rem; }

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background: #0f172a;
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stTextInput label,
section[data-testid="stSidebar"] .stTextArea label {
    color: #94a3b8 !important;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
}

/* Animated pulse for running state */
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
.running-badge {
    display: inline-block;
    background: #2563eb;
    color: white;
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 20px;
    font-weight: 600;
    animation: pulse 1.2s ease-in-out infinite;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 PipelineDoc")
    st.markdown("---")

    tool = st.selectbox(
        "Pipeline tool",
        options=["dbt", "airflow", "fivetran"],
        format_func=lambda t: f"{TOOL_ICONS[t]}  {t.upper()}",
    )

    st.markdown(" ")
    log_source = st.radio(
        "Log source",
        ["Use sample log", "Paste custom JSON"],
        index=0,
    )

    payload = None
    if log_source == "Use sample log":
        payload = SAMPLES[tool]
        with st.expander("Preview sample payload"):
            st.json(payload)
    else:
        raw_json = st.text_area(
            "Raw JSON payload",
            height=260,
            placeholder='{\n  "jobName": "my_pipeline",\n  ...\n}',
        )
        if raw_json.strip():
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")

    st.markdown(" ")
    slack_channel = st.text_input("Slack channel", value="#data-alerts")

    st.markdown(" ")
    run_btn = st.button(
        "▶  Diagnose Failure",
        type="primary",
        disabled=payload is None,
        use_container_width=True,
    )

    st.markdown("---")
    st.markdown("**Services**")
    services = {
        "Orchestrator": "http://localhost:8000/health",
        "Log Collector": f"{LOG_COLLECTOR}/health",
        "Diagnosis": f"{DIAGNOSIS}/health",
        "Ownership": f"{OWNERSHIP}/health",
        "Notification": f"{NOTIFICATION}/health",
    }
    if st.button("Check health", use_container_width=True):
        for name, url in services.items():
            try:
                r = httpx.get(url, timeout=3)
                st.success(f"✅ {name}")
            except Exception:
                st.error(f"❌ {name} — offline")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-bar">
  <div>
    <p class="header-title">🔍 PipelineDoc</p>
    <p class="header-subtitle">
      AI-powered pipeline failure diagnosis · From stack trace to root cause in seconds
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Pipeline stage tracker ────────────────────────────────────────────────────
def stage_strip(states: dict):
    """states: {1: 'pending'|'active'|'done'|'error', ...}"""
    labels = {
        1: ("📥", "Log Collector"),
        2: ("🧠", "Diagnosis"),
        3: ("👤", "Owner Lookup"),
        4: ("📣", "Notify"),
    }
    boxes = ""
    for i, (emoji, name) in labels.items():
        css = states.get(i, "pending")
        boxes += f'<div class="stage-box {css}"><span class="stage-num">{emoji}</span>Agent {i} · {name}</div>'
    st.markdown(f'<div class="pipeline-strip">{boxes}</div>', unsafe_allow_html=True)

# ── Default idle state ────────────────────────────────────────────────────────
if "result" not in st.session_state:
    st.session_state.result = None
if "stages" not in st.session_state:
    st.session_state.stages = {1: "pending", 2: "pending", 3: "pending", 4: "pending"}

stage_strip(st.session_state.stages)

if not run_btn and st.session_state.result is None:
    st.markdown("""
    <div style="text-align:center; padding: 3rem 0; color: #94a3b8;">
      <div style="font-size: 3rem;">🛠️</div>
      <div style="font-size: 1.1rem; margin-top: 0.5rem;">
        Select a tool and click <strong>Diagnose Failure</strong> to begin.
      </div>
      <div style="font-size: 0.85rem; margin-top: 0.4rem;">
        The agent pipeline will parse logs, identify the root cause, find the owner, and draft a Slack alert.
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── Run the pipeline ──────────────────────────────────────────────────────────
if run_btn and payload is not None:
    st.session_state.result = None
    stages = {1: "pending", 2: "pending", 3: "pending", 4: "pending"}
    error_msg = None

    stage_placeholder = st.empty()
    status_placeholder = st.empty()

    _STAGE_LABELS = {
        1: ("📥", "Log Collector"),
        2: ("🧠", "Diagnosis"),
        3: ("👤", "Owner Lookup"),
        4: ("📣", "Notify"),
    }

    def update_strip(s):
        boxes = ""
        for i, (em, nm) in _STAGE_LABELS.items():
            css = s.get(i, "pending")
            boxes += (
                f'<div class="stage-box {css}">'
                f'<span class="stage-num">{em}</span>'
                f"Agent {i} · {nm}</div>"
            )
        stage_placeholder.markdown(
            f'<div class="pipeline-strip">{boxes}</div>',
            unsafe_allow_html=True,
        )

    # Wipe initial strip
    stage_placeholder.empty()

    with status_placeholder.container():
        # ── Agent 1: Log Collector ────────────────────────────────────────────
        stages[1] = "active"
        update_strip(stages)
        with st.status("🔍 Agent 1 — Parsing & enriching logs…", expanded=True) as s1:
            try:
                r = httpx.post(
                    f"{LOG_COLLECTOR}/collect",
                    json={"tool": tool, "raw_payload": payload},
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                normalized = r.json()
                stages[1] = "done"
                update_strip(stages)
                s1.update(label=f"✅ Agent 1 — Log Collector complete", state="complete")
                st.write(f"**Job:** {normalized['job_name']}  |  "
                         f"**Category:** {normalized.get('error_category', '—')}  |  "
                         f"**Severity hint:** {normalized.get('severity_hint', '—')}")
            except Exception as e:
                stages[1] = "error"
                update_strip(stages)
                s1.update(label="❌ Agent 1 — Log Collector failed", state="error")
                error_msg = f"Log Collector error: {e}"
                st.error(error_msg)

        if error_msg:
            st.session_state.stages = stages
            st.stop()

        # ── Agent 2: Diagnosis ────────────────────────────────────────────────
        stages[2] = "active"
        update_strip(stages)
        with st.status("🧠 Agent 2 — Running root cause analysis…", expanded=True) as s2:
            try:
                r = httpx.post(
                    f"{DIAGNOSIS}/diagnose",
                    json=normalized,
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                diagnosis = r.json()
                stages[2] = "done"
                update_strip(stages)
                s2.update(label=f"✅ Agent 2 — Diagnosis complete", state="complete")
                st.write(f"**Severity:** {diagnosis['severity'].upper()}  |  "
                         f"**Confidence:** {diagnosis['confidence'].capitalize()}")
            except Exception as e:
                stages[2] = "error"
                update_strip(stages)
                s2.update(label="❌ Agent 2 — Diagnosis failed", state="error")
                error_msg = f"Diagnosis error: {e}"
                st.error(error_msg)

        if error_msg:
            st.session_state.stages = stages
            st.stop()

        # ── Agent 3: Ownership Router ─────────────────────────────────────────
        stages[3] = "active"
        update_strip(stages)
        with st.status("👤 Agent 3 — Resolving owner…", expanded=True) as s3:
            try:
                r = httpx.post(
                    f"{OWNERSHIP}/route",
                    json={"job_name": normalized["job_name"]},
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                owner = r.json()
                stages[3] = "done"
                update_strip(stages)
                s3.update(label=f"✅ Agent 3 — Owner resolved", state="complete")
                st.write(f"**Owner:** {owner['name']}  |  **Handle:** {owner['slack_handle']}")
            except Exception as e:
                stages[3] = "error"
                update_strip(stages)
                s3.update(label="❌ Agent 3 — Ownership lookup failed", state="error")
                error_msg = f"Ownership error: {e}"
                st.error(error_msg)

        if error_msg:
            st.session_state.stages = stages
            st.stop()

        # ── Agent 4: Notification ─────────────────────────────────────────────
        stages[4] = "active"
        update_strip(stages)
        with st.status("📣 Agent 4 — Sending Slack notification…", expanded=True) as s4:
            try:
                r = httpx.post(
                    f"{NOTIFICATION}/notify",
                    json={
                        "diagnosis": diagnosis,
                        "owner": owner,
                        "slack_channel": slack_channel,
                    },
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                notification = r.json()
                stages[4] = "done"
                update_strip(stages)
                mode = notification.get("mode", "unknown")
                label = "✅ Agent 4 — Slack notification sent" if mode == "slack" else "✅ Agent 4 — Notification logged (console mode)"
                s4.update(label=label, state="complete")
                st.write(f"**Mode:** {mode}  |  **Channel:** {notification.get('channel', slack_channel)}")
            except Exception as e:
                stages[4] = "error"
                update_strip(stages)
                s4.update(label="❌ Agent 4 — Notification failed", state="error")
                error_msg = f"Notification error: {e}"
                st.error(error_msg)

    st.session_state.stages = stages
    if not error_msg:
        st.session_state.result = {
            "normalized": normalized,
            "diagnosis": diagnosis,
            "owner": owner,
            "notification": notification,
        }
        st.rerun()

# ── Display results ───────────────────────────────────────────────────────────
if st.session_state.result:
    r = st.session_state.result
    d = r["diagnosis"]
    o = r["owner"]
    n = r["notification"]

    sev   = d.get("severity", "medium")
    conf  = d.get("confidence", "medium")
    scfg  = SEVERITY_CONFIG.get(sev, SEVERITY_CONFIG["medium"])
    ccfg  = CONFIDENCE_CONFIG.get(conf, CONFIDENCE_CONFIG["medium"])

    st.markdown("---")

    # ── Headline card ─────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="result-card" style="
        background:{scfg['bg']};
        border-left-color:{scfg['color']};
    ">
      <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1rem;">
        <span style="font-size:2rem;">{scfg['emoji']}</span>
        <div>
          <div style="font-size:1.4rem; font-weight:800; color:#1e293b;">{d['job_name']}</div>
          <div style="font-size:0.85rem; color:#64748b;">
            {TOOL_ICONS.get(d['tool'], '⚙️')}&nbsp;{d['tool'].upper()}
            &nbsp;·&nbsp;{d.get('environment','production')}
            &nbsp;·&nbsp;{d.get('timestamp','')}
          </div>
        </div>
        <div style="margin-left:auto; text-align:right;">
          <span style="
            background:{scfg['color']}22;
            color:{scfg['color']};
            border:1.5px solid {scfg['color']};
            padding:4px 14px;
            border-radius:20px;
            font-size:0.78rem;
            font-weight:700;
            letter-spacing:1px;
          ">{scfg['label']} SEVERITY</span>
        </div>
      </div>
      <div class="meta-grid">
        <div class="meta-item">
          <div class="section-label">Error Category</div>
          <div class="section-value">{d.get('error_category','Unknown')}</div>
        </div>
        <div class="meta-item">
          <div class="section-label">Affected Component</div>
          <div class="section-value">{d.get('affected_component','Unknown')}</div>
        </div>
        <div class="meta-item">
          <div class="section-label">Confidence</div>
          <div class="section-value">{ccfg['emoji']} {ccfg['label']}</div>
        </div>
      </div>
      <div style="margin-bottom:0.6rem;">
        <div class="section-label">Pre-Summary (Log Collector)</div>
        <div class="section-value" style="color:#475569;">{d.get('summary','—')}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Root cause + fix ──────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:1.3rem;">
          <div class="section-label">🔍 Root Cause</div>
          <div class="section-value">{d['root_cause']}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:1.3rem;">
          <div class="section-label">🔧 Suggested Fix</div>
          <div class="section-value">{d['suggested_fix']}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(" ")

    # ── Owner + notification status ───────────────────────────────────────────
    col3, col4 = st.columns([1, 2])

    with col3:
        st.markdown(f"""
        <div style="background:#f0fdf4; border:1px solid #86efac; border-radius:12px; padding:1.2rem;">
          <div class="section-label">👤 Owner</div>
          <div style="font-size:1.1rem; font-weight:700; color:#15803d; margin:0.3rem 0;">{o['name']}</div>
          <div style="font-size:0.9rem; color:#166534;">{o['slack_handle']}</div>
          <div style="font-size:0.8rem; color:#64748b; margin-top:0.3rem;">{o.get('team','')}</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        mode = n.get("mode", "unknown")
        if mode == "slack":
            notif_html = f"""
            <div style="background:#f0fdf4; border:1px solid #86efac; border-radius:12px; padding:1.2rem;">
              <div class="section-label">📣 Notification</div>
              <div style="font-size:1rem; color:#15803d; font-weight:600; margin:0.3rem 0;">
                ✅ Sent to Slack
              </div>
              <div style="font-size:0.85rem; color:#166534;">
                Channel: <strong>{n.get('channel', slack_channel)}</strong>
                &nbsp;·&nbsp; ts: <code>{n.get('ts', '—')}</code>
              </div>
            </div>
            """
        else:
            notif_html = f"""
            <div style="background:#fffbeb; border:1px solid #fcd34d; border-radius:12px; padding:1.2rem;">
              <div class="section-label">📣 Notification</div>
              <div style="font-size:1rem; color:#92400e; font-weight:600; margin:0.3rem 0;">
                🖥️ Console mode (no Slack token)
              </div>
              <div style="font-size:0.85rem; color:#78350f;">
                Set <code>SLACK_BOT_TOKEN</code> in .env to enable real Slack posting.
              </div>
            </div>
            """
        st.markdown(notif_html, unsafe_allow_html=True)

    st.markdown(" ")

    # ── Slack message preview ─────────────────────────────────────────────────
    with st.expander("📱 Slack message preview", expanded=True):
        sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
        conf_label = {"high": "✅ High", "medium": "❓ Medium", "low": "⚠️ Low"}.get(conf, conf)
        run_id_line = f"Run: `{d['run_id']}`  ·  " if d.get("run_id") else ""

        st.markdown(f"""
        <div class="slack-preview" style="border-left-color:{scfg['color']};">
          <div class="slack-header">{sev_emoji} &nbsp;Pipeline Failure — {d['job_name']}</div>
          <hr style="border-color:#36393e; margin:0.6rem 0;">
          <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:0.8rem; margin-bottom:0.8rem;">
            <div><div class="slack-field-label">TOOL</div><div class="slack-field-value">{d['tool'].upper()}</div></div>
            <div><div class="slack-field-label">ENVIRONMENT</div><div class="slack-field-value">{d.get('environment','production')}</div></div>
            <div><div class="slack-field-label">ERROR CATEGORY</div><div class="slack-field-value">{d.get('error_category','Unknown')}</div></div>
            <div><div class="slack-field-label">AFFECTED COMPONENT</div><div class="slack-field-value">{d.get('affected_component','Unknown')}</div></div>
            <div><div class="slack-field-label">SEVERITY</div><div class="slack-field-value">{sev.capitalize()}</div></div>
            <div><div class="slack-field-label">OWNER</div><div class="slack-field-value">{o['slack_handle']}</div></div>
          </div>
          <hr style="border-color:#36393e; margin:0.6rem 0;">
          <div class="slack-section-title">🔍 Root Cause</div>
          <div style="margin-top:0.3rem;">{d['root_cause']}</div>
          <div class="slack-section-title" style="margin-top:0.8rem;">🔧 Suggested Fix</div>
          <div style="margin-top:0.3rem;">{d['suggested_fix']}</div>
          <hr style="border-color:#36393e; margin:0.6rem 0;">
          <div class="slack-footer">
            Diagnosed by PipelineDoc AI &nbsp;·&nbsp;
            Confidence: {conf_label} &nbsp;·&nbsp;
            Tagging {o['slack_handle']} &nbsp;·&nbsp;
            {run_id_line}Failed at: {d.get('timestamp','—')}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Expandable raw data ───────────────────────────────────────────────────
    st.markdown(" ")
    with st.expander("🗂️ Raw agent outputs (JSON)"):
        tabs = st.tabs(["Normalized (Agent 1)", "Diagnosis (Agent 2)", "Owner (Agent 3)", "Notification (Agent 4)"])
        with tabs[0]:
            st.json(r["normalized"])
        with tabs[1]:
            st.json(r["diagnosis"])
        with tabs[2]:
            st.json(r["owner"])
        with tabs[3]:
            st.json(r["notification"])

    # ── Relevant log lines ────────────────────────────────────────────────────
    relevant = r["normalized"].get("relevant_logs", [])
    if relevant:
        with st.expander(f"📋 Relevant log lines filtered by Agent 1 ({len(relevant)} lines)"):
            st.code("\n".join(relevant), language="text")