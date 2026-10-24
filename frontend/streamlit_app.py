"""
Enterprise IT Support Agentic RAG Copilot - Streamlit UI
Run:  streamlit run streamlit_app.py
Backend:  uvicorn app.main:app --reload
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api")
AUDIT_DB = os.getenv("AUDIT_DB_PATH", os.path.join("data", "audit.db"))

st.set_page_config(
    page_title="IT Support Copilot",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

SOURCE_LABELS = {
    "private_kb": ("📚 Company Knowledge Base", "green"),
    "web": ("🌐 Web Search", "blue"),
    "web_search": ("🌐 Web Search", "blue"),
    "direct": ("💬 Direct reply", "violet"),
    "insufficient_evidence": ("⚠️ Not enough evidence", "orange"),
    "none": ("⚠️ No source", "orange"),
}

EXAMPLES = [
    ("🔐", "Reset password", "How do I reset my password?"),
    ("🌐", "VPN not connecting", "My VPN is not connecting, what should I do?"),
    ("📶", "Wi-Fi drops", "Wi-Fi keeps disconnecting on my laptop"),
    ("📧", "Email on phone", "How do I set up company email on my phone?"),
]

# ----------------------------------------------------------------------------
# Styling (injected inline, no external CSS files)
# ----------------------------------------------------------------------------
st.markdown(
    """
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
#MainMenu, footer {visibility: hidden;}

/* Hero */
.hero {
    padding: 2.2rem 2rem; border-radius: 20px; margin-bottom: 1.2rem;
    background: linear-gradient(135deg, #1e3a8a 0%, #4f46e5 45%, #9333ea 100%);
    box-shadow: 0 10px 30px rgba(79, 70, 229, 0.35);
}
.hero h1 {margin: 0; font-size: 2.2rem; color: #fff; font-weight: 800;}
.hero p {margin: .5rem 0 1rem 0; color: #e0e7ff; font-size: 1.05rem;}
.chip {
    display: inline-block; padding: .25rem .7rem; margin: 0 .35rem .35rem 0;
    border-radius: 999px; font-size: .78rem; font-weight: 600;
    background: rgba(255,255,255,.16); color: #fff;
    border: 1px solid rgba(255,255,255,.28);
}

/* Chat */
[data-testid="stChatMessage"] {
    border-radius: 16px; padding: 1rem 1.1rem; margin-bottom: .6rem;
    border: 1px solid rgba(148,163,184,.18);
    background: rgba(30,41,59,.45);
}

/* Cards / metrics */
[data-testid="stMetric"] {
    background: rgba(30,41,59,.55); padding: 1rem 1.1rem; border-radius: 14px;
    border: 1px solid rgba(148,163,184,.18);
}

/* Buttons */
.stButton > button {
    border-radius: 12px; border: 1px solid rgba(148,163,184,.3);
    transition: all .15s ease;
}
.stButton > button:hover {
    border-color: #6366f1; transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(99,102,241,.25);
}

/* Sidebar */
[data-testid="stSidebar"] {border-right: 1px solid rgba(148,163,184,.15);}
.brand {font-size: 1.35rem; font-weight: 800; margin-bottom: .1rem;}
.brand-sub {color: #94a3b8; font-size: .85rem; margin-bottom: 1rem;}
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("pending", None)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def call_chat(question: str) -> dict:
    t0 = time.perf_counter()
    r = requests.post(f"{API_BASE}/chat", json={"question": question}, timeout=120)
    elapsed = time.perf_counter() - t0
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise RuntimeError(f"{r.status_code}: {detail}")
    data = r.json()
    data["latency_s"] = round(elapsed, 2)
    return data


def type_out(text: str):
    """Generator for a smooth typing effect."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.015)


def render_meta(msg: dict) -> None:
    source = msg.get("source_used", "none")
    label, color = SOURCE_LABELS.get(source, (f"ℹ️ {source}", "gray"))
    st.badge(label, color=color)

    c1, c2, c3 = st.columns(3)
    c1.caption(f"⏱️ {msg.get('latency_s', '-')} s")
    c2.caption(f"📎 {len(msg.get('citations', []))} source(s)")
    if msg.get("rewritten_query"):
        c3.caption(f"🔎 {msg['rewritten_query']}")

    citations = msg.get("citations", [])
    if citations:
        with st.expander(f"📎 Sources ({len(citations)})"):
            for c in citations:
                title = c.get("title", "source")
                url = c.get("url", "")
                kind = c.get("type", "")
                line = f"[{title}]({url})" if url else f"**{title}**"
                st.markdown(f"- {line}  `{kind}`")

    trace = msg.get("trace", [])
    if trace:
        with st.expander("🧠 Agent reasoning trace"):
            for i, step in enumerate(trace, 1):
                st.markdown(f"**{i}.** {step}")


def load_audit() -> pd.DataFrame:
    if not os.path.exists(AUDIT_DB):
        return pd.DataFrame()
    con = sqlite3.connect(AUDIT_DB)
    try:
        df = pd.read_sql_query(
            "SELECT id, created_at, question, source_used, trace_json "
            "FROM query_audit ORDER BY id DESC",
            con,
        )
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df["steps"] = df["trace_json"].apply(lambda t: len(json.loads(t)) if t else 0)
    return df


# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="brand">🛠️ IT Copilot</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="brand-sub">Agentic RAG for enterprise IT support</div>',
        unsafe_allow_html=True,
    )

    answers = [m for m in st.session_state.messages if m["role"] == "assistant"]
    st.subheader("This session")
    s1, s2 = st.columns(2)
    s1.metric("Questions", len(answers))
    if answers:
        lat = [m["latency_s"] for m in answers if m.get("latency_s")]
        s2.metric("Avg time", f"{sum(lat) / len(lat):.1f}s" if lat else "-")
        kb = sum(1 for m in answers if m.get("source_used") == "private_kb")
        st.progress(kb / len(answers), text=f"{kb}/{len(answers)} answered from company KB")
    else:
        s2.metric("Avg time", "-")

    st.divider()
    st.subheader("Tech stack")
    st.markdown(
        "`FastAPI` `LangGraph` `Groq` `Gemini Embeddings` "
        "`Pinecone` `Tavily` `SQLite` `Streamlit`"
    )

    st.divider()
    if st.button("🗑️ New chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ----------------------------------------------------------------------------
# Hero
# ----------------------------------------------------------------------------
st.markdown(
    """
<div class="hero">
  <h1>🛠️ Enterprise IT Support Copilot</h1>
  <p>Instant, grounded answers from your company knowledge base, with live web search as a safety net.</p>
  <span class="chip">🤖 Agentic RAG</span>
  <span class="chip">📚 Cited answers</span>
  <span class="chip">🔍 Self-correcting retrieval</span>
  <span class="chip">🧾 Full audit trail</span>
</div>
""",
    unsafe_allow_html=True,
)

tab_chat, tab_admin, tab_analytics = st.tabs(
    ["💬 Ask Copilot", "🔐 Knowledge Base", "📊 Analytics"]
)

# ---------------------------- Chat tab --------------------------------------
with tab_chat:
    if not st.session_state.messages:
        st.markdown("#### 👋 What can I help you with?")
        cols = st.columns(4)
        for i, (icon, title, prompt) in enumerate(EXAMPLES):
            with cols[i]:
                with st.container(border=True):
                    st.markdown(f"### {icon}")
                    st.markdown(f"**{title}**")
                    if st.button("Ask", key=f"ex_{i}", use_container_width=True):
                        st.session_state.pending = prompt
                        st.rerun()

    for msg in st.session_state.messages:
        avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                render_meta(msg)

    user_input = st.chat_input("Ask an IT support question...")
    question = user_input or st.session_state.pending
    st.session_state.pending = None

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(question)

        with st.chat_message("assistant", avatar="🤖"):
            try:
                with st.spinner("Searching knowledge base and thinking..."):
                    data = call_chat(question)

                msg = {
                    "role": "assistant",
                    "content": data["answer"],
                    "source_used": data.get("source_used", "none"),
                    "citations": data.get("citations", []),
                    "trace": data.get("trace", []),
                    "rewritten_query": data.get("rewritten_query"),
                    "latency_s": data.get("latency_s"),
                }
                st.write_stream(type_out(msg["content"]))
                render_meta(msg)
                st.session_state.messages.append(msg)
            except requests.exceptions.ConnectionError:
                st.error("Cannot reach the server right now. Please try again in a moment.")
            except Exception as exc:
                st.error(f"Something went wrong: {exc}")

# ---------------------------- Knowledge base tab ----------------------------
with tab_admin:
    st.subheader("Knowledge Base Management")
    st.caption("Upload documents to index them into the vector database. Admin key required.")

    left, right = st.columns([2, 1])
    with left:
        with st.container(border=True):
            admin_key = st.text_input("Admin key", type="password")
            uploaded_files = st.file_uploader(
                "Drop documents here",
                type=["txt", "md", "pdf"],
                accept_multiple_files=True,
            )
            if st.button(
                "🚀 Index documents", type="primary", disabled=not uploaded_files
            ):
                progress = st.progress(0.0, text="Starting...")
                results = []
                for i, f in enumerate(uploaded_files, 1):
                    progress.progress((i - 1) / len(uploaded_files), text=f"Indexing {f.name}...")
                    try:
                        r = requests.post(
                            f"{API_BASE}/ingest",
                            headers={"x-admin-key": admin_key},
                            files={"file": (f.name, f.getvalue())},
                            timeout=300,
                        )
                        if r.ok:
                            j = r.json()
                            results.append(
                                {"File": j["file"], "Chunks": j["chunks"], "Status": "✅ Indexed"}
                            )
                        else:
                            results.append(
                                {"File": f.name, "Chunks": 0, "Status": f"❌ {r.status_code}"}
                            )
                    except requests.RequestException as exc:
                        results.append({"File": f.name, "Chunks": 0, "Status": f"❌ {exc}"})
                progress.progress(1.0, text="Done")
                st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
    with right:
        with st.container(border=True):
            st.markdown("**Supported formats**")
            st.markdown("`.txt`  `.md`  `.pdf`")
            st.markdown("**Pipeline**")
            st.markdown("Upload → Chunk → Embed → Index")

# ---------------------------- Analytics tab ---------------------------------
with tab_analytics:
    st.subheader("Usage Analytics")
    st.caption("Live from the audit log.")

    df = load_audit()
    if df.empty:
        st.info("No queries logged yet. Ask a question in the chat tab first.")
    else:
        total = len(df)
        kb_hits = int((df["source_used"] == "private_kb").sum())
        today_utc = datetime.now(timezone.utc).date()
        today = int((df["created_at"].dt.date == today_utc).sum())

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total queries", total)
        m2.metric("Answered from KB", f"{kb_hits / total:.0%}")
        m3.metric("Queries today", today)
        m4.metric("Avg agent steps", f"{df['steps'].mean():.1f}")

        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown("**Answer source**")
                st.bar_chart(df["source_used"].value_counts())
        with c2:
            with st.container(border=True):
                st.markdown("**Queries per day**")
                st.line_chart(df.groupby(df["created_at"].dt.date).size())

        st.markdown("**Recent queries**")
        st.dataframe(
            df[["created_at", "question", "source_used", "steps"]].head(50),
            use_container_width=True,
            hide_index=True,
        )