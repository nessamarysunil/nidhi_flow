import os
import io
import re
import hashlib
import datetime
import sqlite3
import streamlit as st
import pandas as pd
from gtts import gTTS

from core.db import (
    init_db,
    get_members,
    get_active_meeting,
    get_db_connection,
    DB_PATH,
    add_member,
    clear_members,
    load_sample_members,
    seed_sample_members
)
from core.ledger import (
    GENESIS_HASH,
    get_latest_hash,
    add_ledger_entry,
    verify_chain,
    calculate_derived_balances,
    reset_ledger,
    validate_loan_confirmation,
    validate_transaction_logic,
    delete_latest_ledger_entry
)
from core.fingerprint import (
    hash_to_fingerprint,
    hash_to_fingerprint_en,
    hash_to_fingerprint_spoken
)
from core.gnani_client import (
    GNANI_API_KEY,
    GNANI_STT_URL,
    process_voice_entry,
    normalize_amount,
    match_member_from_text,
    match_member_from_roster,
    detect_event_type,
    parse_voice_onboarding,
    extract_onboarding_from_text,
    transcribe_clip
)

# ==============================================================================
# Page Configuration: Centered, Calm, Collapsible Sidebar
# ==============================================================================
st.set_page_config(
    page_title="നിധി ഫ്ലോ | NidhiFlow — Community Voice Passbook",
    page_icon="🌸",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Initialize database schema and seeds
init_db()

# Bilingual & Pure Malayalam Mappings
EVENT_LABELS = {
    "thrift": "സമ്പാദ്യം — Thrift Savings",
    "loan_disbursement": "വായ്പ — Loan Disbursement",
    "repayment": "തിരിച്ചടവ് — Loan Repayment",
    "fine": "പിഴ — Meeting Fine"
}

EVENT_PURE_ML = {
    "thrift": "സമ്പാദ്യം",
    "loan_disbursement": "വായ്പ നൽകൽ",
    "repayment": "വായ്പാ തിരിച്ചടവ്",
    "fine": "പിഴ"
}

ROLE_LABELS = {
    "secretary": "സെക്രട്ടറി (Secretary)",
    "president": "പ്രസിഡന്റ് (President)",
    "member": "അംഗം (Member)"
}

# ==============================================================================
# Malayalam Typography & Proportional Proportions (CSS)
# ==============================================================================
st.markdown("""
<style>
    /* Google Fonts for Malayalam + English + Material Symbols */
    @import url('https://fonts.googleapis.com/css2?family=Manjari:wght@400;700&family=Noto+Sans+Malayalam:wght@400;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400,0,0');

    body, p, label, h1, h2, h3, h4, h5, h6, input, select, textarea, [data-testid="stMarkdownContainer"], .stSelectbox, .stTextInput, .stRadio {
        font-family: 'Noto Sans Malayalam', 'Manjari', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: #1F2937;
        line-height: 1.5;
    }

    /* Preserve Streamlit Material Icons & Expander Arrows */
    [data-testid="stIconMaterial"],
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons,
    [translate="no"],
    [data-testid="stExpanderToggleIcon"],
    [data-testid="stExpanderToggleIcon"] *,
    [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded' !important;
        font-feature-settings: 'liga' 1 !important;
        -webkit-font-feature-settings: 'liga' 1 !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        white-space: nowrap !important;
        word-wrap: normal !important;
        direction: ltr !important;
        display: inline-block !important;
        line-height: 1 !important;
    }

    [data-testid="stExpander"] summary {
        font-size: 0.92rem !important;
        font-weight: 600 !important;
        color: #4B5563 !important;
        display: flex !important;
        align-items: center !important;
        gap: 8px !important;
    }

    [data-testid="stExpanderToggleIcon"] {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        min-width: 22px !important;
        width: 22px !important;
        height: 22px !important;
        flex-shrink: 0 !important;
        margin-right: 4px !important;
    }

    [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] {
        display: inline-flex !important;
        align-items: center !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p {
        margin: 0 !important;
        padding: 0 !important;
        display: inline !important;
        line-height: 1.4 !important;
    }

    /* Audio Input: Full container width and zero clipping of waveform/error banners */
    [data-testid="stAudioInput"],
    div[data-testid="stAudioInput"] > div,
    [data-testid="stAudioInput"] * {
        max-width: 100% !important;
        overflow: visible !important;
    }
    [data-testid="stAudioInput"] {
        width: 100% !important;
        height: auto !important;
        min-height: auto !important;
        margin-bottom: 0.5rem !important;
    }

    /* Constrained container width for crisp, focused reading (780px) */
    .block-container {
        max-width: 780px !important;
        padding-top: 1.5rem !important;
        padding-bottom: 3.5rem !important;
    }

    /* Hide Streamlit header anchor link icons */
    [data-testid="stHeaderActionElements"],
    a.anchorjs-link,
    .stHeadingAnchor {
        display: none !important;
    }

    /* Form Labels & Captions: Proportional Proportions */
    [data-testid="stWidgetLabel"] label, label {
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        color: #374151 !important;
        margin-bottom: 4px !important;
    }
    .stCaption, p.caption {
        font-size: 0.82rem !important;
        color: #6B7280 !important;
        line-height: 1.4 !important;
    }

    /* Card Containers */
    .nidhi-card, div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF;
        border: 1px solid #E5DEC9 !important;
        border-radius: 14px !important;
        padding: 20px 22px !important;
        box-shadow: 0 3px 12px -2px rgba(136, 19, 55, 0.04) !important;
        margin-bottom: 1.2rem !important;
        line-height: 1.5;
    }

    /* Compact Hero Banner: Inline Icon + 1.65rem Title + 16px 24px padding */
    .nidhi-header-box {
        background: linear-gradient(135deg, #FFFDF9 0%, #FBF6EE 100%);
        border: 1px solid #E5DEC9;
        border-radius: 14px;
        padding: 16px 24px;
        margin-bottom: 1.2rem;
        box-shadow: 0 2px 8px -1px rgba(136, 19, 55, 0.04);
    }

    .main-title {
        font-size: 1.65rem;
        font-weight: 700;
        color: #881337;
        margin-bottom: 0.1rem;
        line-height: 1.25;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .main-tagline {
        font-size: 0.98rem;
        font-weight: 600;
        color: #92400E;
        font-style: italic;
        margin-bottom: 0.35rem;
    }

    .main-subtitle {
        font-size: 0.86rem;
        color: #57534E;
        line-height: 1.4;
    }

    .section-title {
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        color: #1F2937 !important;
        margin-top: 0.2rem !important;
        margin-bottom: 0.5rem !important;
        line-height: 1.4 !important;
    }

    /* Meeting Info Pill */
    .meeting-pill {
        background-color: #F3EFE6;
        border: 1px solid #E5DEC9;
        border-radius: 10px;
        padding: 0.5rem 0.9rem;
        font-size: 0.88rem;
        color: #44403C;
        display: inline-block;
        margin-top: 0.5rem;
        line-height: 1.4;
    }

    /* 6-Word Spoken Meeting Fingerprint Banner */
    .fingerprint-card {
        background: linear-gradient(135deg, #881337 0%, #9F1239 50%, #B45309 100%);
        color: #FFFBEB;
        padding: 18px 22px;
        border-radius: 14px;
        box-shadow: 0 4px 14px -2px rgba(136, 19, 55, 0.2);
        border: 1px solid rgba(251, 191, 36, 0.4);
        margin-bottom: 1.2rem;
        line-height: 1.4;
    }
    .fingerprint-title {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #FDE68A;
        font-weight: 600;
    }
    .fingerprint-words {
        font-size: 1.25rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        margin-top: 0.3rem;
        color: #FFFFFF;
        text-shadow: 0 1px 2px rgba(0,0,0,0.25);
        line-height: 1.35;
    }
    .fingerprint-subtitle {
        font-size: 0.85rem;
        color: #FDE68A;
        font-style: italic;
        margin-top: 0.2rem;
        opacity: 0.95;
    }

    /* Professional Flexbox Name-Tag Pills */
    .roster-flex {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 8px 0 12px 0;
    }
    .member-pill {
        white-space: nowrap;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.88rem;
        font-weight: 600;
        line-height: 1;
    }
    .pill-secretary {
        background-color: #FDF2F4;
        border: 1px solid #FBCFE8;
        color: #881337;
    }
    .pill-president {
        background-color: #FFFBEB;
        border: 1px solid #FDE68A;
        color: #92400E;
    }
    .pill-member {
        background-color: #FFFFFF;
        border: 1px solid #E5DEC9;
        color: #374151;
    }

    /* Streamlit Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #E5DEC9;
        padding-bottom: 2px;
        margin-bottom: 1.2rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.98rem !important;
        font-weight: 600 !important;
        color: #57534E !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 8px 16px !important;
        background-color: transparent !important;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        color: #881337 !important;
        border-bottom: 3px solid #881337 !important;
        background-color: #FDF9F0 !important;
    }

    /* Fix for metric clipping / ₹0.... truncation */
    div[data-testid="stMetricValue"] {
        color: #881337 !important;
        font-weight: 700 !important;
        font-size: 1.35rem !important;
        white-space: nowrap !important;
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.25 !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.86rem !important;
        color: #4B5563 !important;
        font-weight: 600 !important;
        white-space: normal !important;
        line-height: 1.3 !important;
    }
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E5DEC9;
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
    }

    /* Buttons: Accessible, Warm & Proportional */
    .stButton>button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        padding: 0.55rem 1.1rem !important;
        transition: all 0.2s ease !important;
        font-family: 'Noto Sans Malayalam', 'Manjari', sans-serif !important;
        white-space: normal !important;
        height: auto !important;
        line-height: 1.4 !important;
    }

    /* Primary Buttons: High Contrast Crisp White Text */
    .stButton>button[kind="primary"],
    .stButton>button[data-testid="baseButton-primary"] {
        background-color: #881337 !important;
        color: #FFFFFF !important;
        border: 1px solid #70102E !important;
        box-shadow: 0 3px 8px -1px rgba(136, 19, 55, 0.3) !important;
    }
    .stButton>button[kind="primary"] *,
    .stButton>button[data-testid="baseButton-primary"] * {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    .stButton>button[kind="primary"]:hover,
    .stButton>button[data-testid="baseButton-primary"]:hover {
        background-color: #9F1239 !important;
        color: #FFFFFF !important;
    }

    /* High-Specificity: Force Crisp White Text Inside Maroon Buttons */
    .stButton > button[kind="primary"],
    .stButton > button[kind="primary"] *,
    .stButton > button[kind="primary"] p,
    .stButton > button[kind="primary"] span,
    .stButton > button[kind="primary"] div,
    .stButton > button[data-testid="baseButton-primary"],
    .stButton > button[data-testid="baseButton-primary"] *,
    .stButton > button[data-testid="baseButton-primary"] p,
    .stButton > button[data-testid="baseButton-primary"] span,
    .stButton > button[data-testid="baseButton-primary"] div {
        background-color: #881337 !important;
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
        font-weight: 700 !important;
    }

    .stButton > button[kind="primary"]:hover,
    .stButton > button[kind="primary"]:hover *,
    .stButton > button[data-testid="baseButton-primary"]:hover,
    .stButton > button[data-testid="baseButton-primary"]:hover * {
        background-color: #9F1239 !important;
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
    }

    /* Warm Accessible Status Badges */
    .badge-green {
        background-color: #ECFDF5;
        border: 1.5px solid #10B981;
        color: #065F46;
        padding: 0.45rem 0.9rem;
        border-radius: 8px;
        font-weight: 700;
        display: inline-block;
        font-size: 0.92rem;
        line-height: 1.4;
    }
    .badge-amber {
        background-color: #FFFBEB;
        border: 1.5px solid #F59E0B;
        color: #92400E;
        padding: 0.45rem 0.9rem;
        border-radius: 8px;
        font-weight: 700;
        display: inline-block;
        font-size: 0.92rem;
        line-height: 1.4;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# Helper Functions: Audio Synthesis & Clean Malayalam Read-Back
# ==============================================================================
def synthesize_spoken_scenario(text: str) -> bytes:
    """
    Synthesizes real Malayalam-English spoken speech using gTTS into an in-memory buffer.
    """
    fp = io.BytesIO()
    tts = gTTS(text=text, lang="ml")
    tts.write_to_fp(fp)
    return fp.getvalue()

def generate_readback_audio(member_name: str, event_type: str, amount: float) -> bytes:
    """
    Generates a warm, authentic confirmation read-back in pure Malayalam:
    '{member_name}, {event_pure_ml}, {amount} രൂപ. ഇത് ശരിയാണോ?'
    """
    amt_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
    event_simple = EVENT_PURE_ML.get(event_type, "ഇടപാട്")
    readback_text = f"{member_name}, {event_simple}, {amt_str} രൂപ. ഇത് ശരിയാണോ?"
    fp = io.BytesIO()
    try:
        tts = gTTS(text=readback_text, lang="ml")
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception:
        try:
            tts = gTTS(text=f"{member_name}, {event_simple}, {amt_str} roopa. Ithu shariyaano?", lang="en", tld="co.in")
            tts.write_to_fp(fp)
            return fp.getvalue()
        except Exception:
            return b""

# ==============================================================================
# Session State Initialization
# ==============================================================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "group_name" not in st.session_state:
    st.session_state["group_name"] = ""
if "active_user" not in st.session_state:
    st.session_state["active_user"] = "Leela"
if "active_role" not in st.session_state:
    st.session_state["active_role"] = "secretary"
if "stt_result" not in st.session_state:
    st.session_state["stt_result"] = None
if "current_audio_bytes" not in st.session_state:
    st.session_state["current_audio_bytes"] = None
if "current_clip_hash" not in st.session_state:
    st.session_state["current_clip_hash"] = None
if "verification_result" not in st.session_state:
    st.session_state["verification_result"] = None
if "extracted_onboarding" not in st.session_state:
    st.session_state["extracted_onboarding"] = None
if "onboarding_sample_bytes" not in st.session_state:
    st.session_state["onboarding_sample_bytes"] = None
if "onboarding_sample_text" not in st.session_state:
    st.session_state["onboarding_sample_text"] = None

# Active meeting & roster data
active_meeting = get_active_meeting()
meeting_id = active_meeting["id"]
meeting_date = active_meeting["meeting_date"]
members = get_members()
member_names = [m["name"] for m in members]
member_dict = {m["name"]: m["id"] for m in members}
member_role_dict = {m["name"]: m["role"] for m in members}

# ==============================================================================
# Collapsible Sidebar: Always Accessible Roster, Session & Reset Controls
# ==============================================================================
with st.sidebar:
    st.markdown("### 🌸 നിധി ഫ്ലോ സഹചാരി")
    sidebar_grp = st.session_state.get('group_name') or "പേര് നൽകിയിട്ടില്ല (Not set)"
    st.markdown(f"**കൂട്ടായ്മ:** {sidebar_grp}")
    st.markdown(f"**യോഗം (Session):** `#{meeting_id}` &nbsp;|&nbsp; **തീയതി:** `{meeting_date}`")
    if st.session_state.get("logged_in"):
        active_u = st.session_state.get('active_user', 'Leela')
        active_r = ROLE_LABELS.get(st.session_state.get('active_role', 'secretary'), 'അംഗം')
        st.markdown(f"**ലോഗിൻ ചെയ്തത്:** 👤 **{active_u}** — *{active_r}*")
        if st.button("🚪 ഗ്രൂപ്പ് മാറ്റുക / പുറത്തുകടക്കുക (Switch Group / Logout)", use_container_width=True):
            st.session_state["logged_in"] = False
            st.rerun()

    st.markdown("---")
    st.markdown("#### 👥 അംഗങ്ങളുടെ പട്ടിക (SHG Roster)")
    for m in members:
        badge = "🔑" if m["role"] == "secretary" else ("👑" if m["role"] == "president" else "👩")
        role_text = ROLE_LABELS.get(m["role"], m["role"])
        st.markdown(f"- {badge} **{m['name']}** — *{role_text}*")

    st.markdown("---")
    st.markdown("#### 🔄 ഡെമോ നിയന്ത്രണം (Demo Controls)")
    st.caption("പാസ്ബുക്ക് നിയന്ത്രണങ്ങൾ (Ledger Controls):")
    if st.button("↩️ അവസാന ഇടപാട് മാറ്റുക | Undo Last", type="secondary", use_container_width=True, key="sb_undo_btn"):
        undo_res = delete_latest_ledger_entry(meeting_id)
        if undo_res["success"]:
            st.toast(f"ഇടപാട് #{undo_res['deleted_entry_id']} ഒഴിവാക്കി!", icon="🗑️")
            st.session_state["verification_result"] = None
            st.rerun()
        else:
            st.toast(undo_res.get("error", "ഒഴിവാക്കാൻ ഇടപാടുകളൊന്നുമില്ല"), icon="⚠️")

    if st.button("🔄 പാസ്ബുക്ക് പുനഃക്രമീകരിക്കുക (Reset Demo)", type="secondary", use_container_width=True):
        reset_ledger(meeting_id)
        st.session_state["stt_result"] = None
        st.session_state["current_audio_bytes"] = None
        st.session_state["current_clip_hash"] = None
        st.session_state["verification_result"] = None
        st.session_state["last_commit_receipt"] = None
        st.toast("പാസ്ബുക്ക് ആദ്യത്തെ അവസ്ഥയിലേക്ക് മാറ്റി (Genesis Block #0)!", icon="🔄")
        st.rerun()

    st.markdown("---")
    st.caption("നിധി ഫ്ലോ — കമ്മ്യൂണിറ്റി ഡിജിറ്റൽ ശബ്ദ പാസ്ബുക്ക്")

# ==============================================================================
# Unified Group Setup & Voice Onboarding Screen (When not logged in)
# ==============================================================================
if not st.session_state.get("logged_in", False):
    # Compact Hero Banner with inline icon and proportional typography
    st.markdown("""
    <div class="nidhi-header-box" style="text-align: center; margin-bottom: 1.2rem;">
        <div class="main-title" style="justify-content: center;">🌸 നിധി ഫ്ലോ | NidhiFlow</div>
        <div class="main-tagline">"ചെറിയ സമ്പാദ്യം, വലിയ പ്രതീക്ഷകൾ"</div>
        <div class="main-subtitle">
            കൂട്ടായ്മകൾക്കായുള്ള ലളിതമായ ശബ്ദ പാസ്ബുക്ക് സഹചാരി | Community Voice Passbook Companion
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<div class="section-title">✨ നിങ്ങളുടെ ഗ്രൂപ്പ് പാസ്ബുക്ക് ആരംഭിക്കുക | Set Up Group Passbook</div>', unsafe_allow_html=True)

        group_entry_mode = st.radio(
            "ഗ്രൂപ്പ് പേര് നൽകുന്ന രീതി:",
            ["🎙️ ശബ്ദത്തിലൂടെ (Speak Group Name)", "⌨️ ടൈപ്പ് ചെയ്ത് (Type Group Name)"],
            horizontal=True,
            key="group_entry_mode_radio"
        )

        if group_entry_mode == "🎙️ ശബ്ദത്തിലൂടെ (Speak Group Name)":
            grp_mic = st.audio_input(
                "🎙️ ഗ്രൂപ്പിന്റെ പേര് പറയുക (ഉദാ: 'സൂര്യകാന്തി കൂട്ടായ്മ'):",
                key="group_name_mic"
            )
            col_g1, col_g2 = st.columns([1.5, 1.5])
            with col_g1:
                if grp_mic is not None:
                    if st.button("🔊 പേര് തിരിച്ചറിയുക | Recognize Group Name", type="primary", use_container_width=True, key="btn_rec_group_name"):
                        with st.spinner("ജ്ഞാനി എഐ ഗ്രൂപ്പിന്റെ പേര് തിരിച്ചറിയുന്നു..."):
                            g_bytes = grp_mic.read()
                            keyterms = ["സൂര്യകാന്തി", "കൂട്ടായ്മ", "സംഘം", "സമിതി", "അയൽക്കൂട്ടം", "ഹരിത", "ശ്രീ", "Suryakanthi", "Koottayma", "Sangham"]
                            g_res = transcribe_clip(g_bytes, output_format="transcribe", keyterms=keyterms)
                            g_tx = g_res.get("transcript", "").strip()
                            if not g_tx:
                                g_res2 = transcribe_clip(g_bytes, output_format="transliterate", keyterms=keyterms)
                                g_tx = g_res2.get("transcript", "").strip()
                            if g_tx:
                                clean_grp = re.sub(r"[.,;!?]+$", "", g_tx).strip()
                                clean_grp = " ".join([w.title() if w.isascii() else w for w in clean_grp.split()])
                                st.session_state["group_name"] = clean_grp
                                st.session_state["group_name_input"] = clean_grp
                                st.toast(f"കൂട്ടായ്മയുടെ പേര് '{clean_grp}' തിരിച്ചറിഞ്ഞു!", icon="✅")
                                st.rerun()
                            else:
                                st.warning("ശബ്ദം വ്യക്തമല്ല. ദയവായി വീണ്ടും പറയുക അല്ലെങ്കിൽ താഴെ ടൈപ്പ് ചെയ്യുക.")
            with col_g2:
                if st.button("⚡ മാതൃകാ പേര് | Sample Name", use_container_width=True, key="btn_sample_group_name"):
                    sample_grp = "സൂര്യകാന്തി കൂട്ടായ്മ"
                    st.session_state["group_name"] = sample_grp
                    st.session_state["group_name_input"] = sample_grp
                    st.toast("മാതൃകാ പേര് 'സൂര്യകാന്തി കൂട്ടായ്മ' നൽകി!", icon="⚡")
                    st.rerun()

        if "group_name_input" not in st.session_state:
            st.session_state["group_name_input"] = st.session_state.get("group_name", "")

        entered_group_name = st.text_input(
            "കൂട്ടായ്മയുടെ / ഗ്രൂപ്പിന്റെ പേര് (പരിശോധിക്കുക / മാറ്റുക):",
            value=st.session_state.get("group_name", ""),
            placeholder="ഉദാ: സൂര്യകാന്തി കൂട്ടായ്മ (Speak or type your Group Name)",
            key="group_name_input"
        )
        st.session_state["group_name"] = entered_group_name

        st.markdown('<div style="height: 6px;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">➕ അംഗങ്ങളെ ചേർക്കുക | Add Group Members</div>', unsafe_allow_html=True)

        # Compact single-select switch so only ONE entry method takes up screen space
        entry_mode = st.radio(
            "ചേർക്കുന്ന രീതി തിരഞ്ഞെടുക്കുക:",
            ["🎙️ ശബ്ദത്തിലൂടെ (By Voice)", "⌨️ ടൈപ്പ് ചെയ്ത് (By Typing)"],
            horizontal=True,
            label_visibility="collapsed"
        )

        if entry_mode == "🎙️ ശബ്ദത്തിലൂടെ (By Voice)":
            voice_audio = st.audio_input(
                "🎙️ കൂട്ടായ്മയുടെ പേരും അംഗങ്ങളുടെ പേരുകളും പറയുക | Speak Group Name & Member Names",
                key="onboarding_mic_input"
            )

            col_sample_btn, col_sample_hint = st.columns([1.8, 1.2])
            with col_sample_btn:
                if st.button("⚡ മാതൃകാ ശബ്ദം ഉപയോഗിക്കുക | Use Sample Voice Audio", use_container_width=True, key="btn_onboarding_sample"):
                    sample_speech = "Suryakanthi Koottayma, Leela secretary, Radha president, Shobhana, Anitha"
                    s_bytes = synthesize_spoken_scenario(sample_speech)
                    st.session_state["onboarding_sample_bytes"] = s_bytes
                    st.session_state["onboarding_sample_text"] = sample_speech
                    st.session_state["extracted_onboarding"] = None
                    st.rerun()
            with col_sample_hint:
                st.caption("🎙️ മൈക്രോഫോൺ ലഭ്യമല്ലെങ്കിൽ മാതൃകാ ശബ്ദം പരീക്ഷിക്കാം.")

            cur_onboarding_audio = voice_audio.read() if voice_audio is not None else st.session_state.get("onboarding_sample_bytes")

            if cur_onboarding_audio:
                st.audio(cur_onboarding_audio, format="audio/wav" if cur_onboarding_audio.startswith(b"RIFF") else "audio/mp3")

                if st.button("🔊 ശബ്ദത്തിൽ നിന്ന് തിരിച്ചറിയുക | Extract Group & Names", type="primary", use_container_width=True, key="btn_extract_voice"):
                    with st.spinner("ജ്ഞാനി എഐ ശബ്ദത്തിൽ നിന്ന് വിവരങ്ങൾ വേർതിരിക്കുന്നു..."):
                        extracted = parse_voice_onboarding(cur_onboarding_audio)

                        # Offline fallback if cloud STT returned empty but sample text is present
                        if not extracted.get("transcript") and st.session_state.get("onboarding_sample_text"):
                            extracted = extract_onboarding_from_text(st.session_state["onboarding_sample_text"])

                        # Auto-update Group Name if extracted from speech!
                        if extracted.get("group_name"):
                            st.session_state["group_name"] = extracted["group_name"]
                            st.session_state["group_name_input"] = extracted["group_name"]

                        st.session_state["extracted_onboarding"] = extracted

            # Extracted preview pills & group badge
            if st.session_state.get("extracted_onboarding"):
                ext_data = st.session_state["extracted_onboarding"]
                ext_group = ext_data.get("group_name")
                ext_members = ext_data.get("members", [])

                if ext_group:
                    st.markdown(
                        f'<div style="background-color: #FFFBEB; border: 1.5px solid #FDE68A; border-radius: 10px; padding: 10px 16px; margin: 8px 0; font-weight: 600; color: #92400E;">'
                        f'🏷️ തിരിച്ചറിഞ്ഞ കൂട്ടായ്മ (Extracted Group): <span style="color: #881337; font-size: 1.05rem;">{ext_group}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                if ext_members:
                    st.markdown('<div class="section-title" style="font-size: 0.95rem !important;">🎯 തിരിച്ചറിഞ്ഞ അംഗങ്ങൾ (Extracted Members):</div>', unsafe_allow_html=True)
                    ext_pills_html = []
                    for m in ext_members:
                        r = m["role"].lower()
                        if r == "secretary":
                            ext_pills_html.append(f'<span class="member-pill pill-secretary">🔑 {m["name"]} • സെക്രട്ടറി</span>')
                        elif r == "president":
                            ext_pills_html.append(f'<span class="member-pill pill-president">👑 {m["name"]} • പ്രസിഡന്റ്</span>')
                        else:
                            ext_pills_html.append(f'<span class="member-pill pill-member">👤 {m["name"]}</span>')
                    st.markdown(f'<div class="roster-flex">{"".join(ext_pills_html)}</div>', unsafe_allow_html=True)

                if ext_members or ext_group:
                    btn_apply_label = "✅ ഈ വിവരങ്ങൾ ചേർക്കുക | Apply Spoken Setup" if ext_group else "✅ ഈ അംഗങ്ങളെ ചേർക്കുക | Add Spoken Members"
                    if st.button(btn_apply_label, type="primary", use_container_width=True, key="btn_apply_spoken_setup"):
                        for m in ext_members:
                            add_member(m["name"], m["role"])
                        if ext_group:
                            st.session_state["group_name"] = ext_group
                            st.session_state["group_name_input"] = ext_group
                        st.session_state["extracted_onboarding"] = None
                        st.session_state["onboarding_sample_bytes"] = None
                        st.session_state["onboarding_sample_text"] = None
                        st.toast("✅ ശബ്ദത്തിൽ നിന്നുള്ള വിവരങ്ങൾ വിജയകരമായി ചേർത്തു!", icon="🎉")
                        st.rerun()

        else:
            # By Typing mode: single aligned 3-column row [3, 2, 1.2]
            col_add1, col_add2, col_add3 = st.columns([3, 2, 1.2])
            with col_add1:
                add_name = st.text_input("അംഗത്തിന്റെ പേര് (Member Name):", placeholder="ഉദാ: ശോഭന, അനിത", key="new_mem_name_input")
            with col_add2:
                add_role = st.selectbox(
                    "ചുമതല (Role):",
                    ["member", "secretary", "president"],
                    format_func=lambda x: ROLE_LABELS.get(x, x),
                    key="new_mem_role_input"
                )
            with col_add3:
                st.write("")
                st.write("")
                if st.button("➕ ചേർക്കുക", use_container_width=True):
                    if add_name and add_name.strip():
                        added = add_member(add_name.strip(), add_role)
                        if added:
                            st.toast(f"അംഗം '{add_name.strip()}' വിജയകരമായി ചേർത്തു!", icon="✅")
                            st.rerun()

        # Roster display with professional Flexbox pills
        st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">👥 അംഗങ്ങൾ | Group Roster</div>', unsafe_allow_html=True)
        current_mems = get_members()
        if current_mems:
            pills_html = []
            for m in current_mems:
                r = m["role"].lower()
                if r == "secretary":
                    pills_html.append(f'<span class="member-pill pill-secretary">🔑 {m["name"]} • സെക്രട്ടറി</span>')
                elif r == "president":
                    pills_html.append(f'<span class="member-pill pill-president">👑 {m["name"]} • പ്രസിഡന്റ്</span>')
                else:
                    pills_html.append(f'<span class="member-pill pill-member">👤 {m["name"]}</span>')
            st.markdown(f'<div class="roster-flex">{"".join(pills_html)}</div>', unsafe_allow_html=True)
        else:
            st.caption("നിലവിൽ അംഗങ്ങളൊന്നും ചേർത്തിട്ടില്ല. മുകളിലെ രീതി ഉപയോഗിച്ച് അംഗങ്ങളെ ചേർക്കുക.")

        # Demo quick-action buttons
        col_demo1, col_demo2 = st.columns(2)
        with col_demo1:
            if st.button("🗑️ അംഗങ്ങളെ പുനഃക്രമീകരിക്കുക | Clear All Members", use_container_width=True, help="ഡെമോയിൽ പുതിയ അംഗങ്ങളുടെ പേര് സംസാരിച്ച് നൽകാൻ പട്ടിക ഒഴിവാക്കുക"):
                clear_members()
                st.session_state["group_name"] = ""
                st.session_state["group_name_input"] = ""
                st.session_state["extracted_onboarding"] = None
                st.session_state["onboarding_sample_bytes"] = None
                st.session_state["onboarding_sample_text"] = None
                st.toast("അംഗങ്ങളുടെ പട്ടിക ഒഴിഞ്ഞു. ഇനി പുതിയ പേരുകൾ പറയാം!", icon="🗑️")
                st.rerun()
        with col_demo2:
            if st.button("⚡ മാതൃകാ ഗ്രൂപ്പ് ലോഡ് ചെയ്യുക | Load Sample Group", use_container_width=True, help="5 മാതൃകാ അംഗങ്ങളെ വീണ്ടും ചേർക്കുക"):
                load_sample_members()
                st.session_state["group_name"] = "സൂര്യകാന്തി കൂട്ടായ്മ (Suryakanthi Collective)"
                st.session_state["group_name_input"] = "സൂര്യകാന്തി കൂട്ടായ്മ (Suryakanthi Collective)"
                st.toast("5 മാതൃകാ അംഗങ്ങളെ വീണ്ടും ചേർത്തു!", icon="⚡")
                st.rerun()

        st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
        # Who is opening the passbook & Open Passbook button
        if current_mems:
            member_options = [
                f"{m['name']} — {ROLE_LABELS.get(m['role'], m['role'])}" if m["role"] in ["secretary", "president"] else f"{m['name']} — അംഗം"
                for m in current_mems
            ]
            selected_login_label = st.selectbox(
                "നിങ്ങൾ ആരാണ്? (Select Who is Opening):",
                member_options,
                index=0,
                key="sel_login_member_unified"
            )
            selected_member_obj = current_mems[member_options.index(selected_login_label)]

            if st.button("✨ പാസ്ബുക്ക് തുറക്കുക | Open Passbook", type="primary", use_container_width=True):
                st.session_state["logged_in"] = True
                grp_val = st.session_state.get("group_name", "").strip()
                st.session_state["group_name"] = grp_val if grp_val else "സൂര്യകാന്തി കൂട്ടായ്മ (Suryakanthi Collective)"
                st.session_state["active_user"] = selected_member_obj["name"]
                st.session_state["active_role"] = selected_member_obj["role"]
                st.rerun()
        else:
            st.warning("⚠️ പാസ്ബുക്ക് തുറക്കുന്നതിന് മുൻപ് ചുരുങ്ങിയത് ഒരു അംഗത്തെയെങ്കിലും ചേർക്കുക.")

    # Stop rendering further when not logged in
    st.stop()

# ==============================================================================
# MAIN WORKSPACE: Header & 6-Word Meeting Code Banner (When logged in)
# ==============================================================================
st.markdown(f"""
<div class="nidhi-header-box">
    <div class="main-title">🌸 നിധി ഫ്ലോ | NidhiFlow</div>
    <div class="main-tagline">"ചെറിയ സമ്പാദ്യം, വലിയ പ്രതീക്ഷകൾ"</div>
    <div class="meeting-pill">
        📍 <b>{st.session_state.get('group_name', 'സൂര്യകാന്തി കൂട്ടായ്മ (Suryakanthi Collective)')}</b> &nbsp;|&nbsp; 
        യോഗം: <b>#{meeting_id}</b> &nbsp;|&nbsp; 
        തീയതി: <b>{meeting_date}</b> &nbsp;|&nbsp; 
        ലോഗിൻ: 👤 <b>{st.session_state.get('active_user', 'Leela')}</b> — {ROLE_LABELS.get(st.session_state.get('active_role', 'secretary'), 'അംഗം')}
    </div>
</div>
""", unsafe_allow_html=True)

# 6-Word Spoken Meeting Fingerprint Banner at Top
latest_hash = get_latest_hash(meeting_id)
fingerprint_ml = hash_to_fingerprint(latest_hash)
fingerprint_en = hash_to_fingerprint_en(latest_hash)
fingerprint_spoken = hash_to_fingerprint_spoken(latest_hash)

if fingerprint_ml == "Genesis Session — Awaiting Block #1":
    st.markdown("""
    <div class="fingerprint-card">
        <div class="fingerprint-title">🔐 ഇന്നത്തെ യോഗ കോഡ് | 6-Word Spoken Meeting Fingerprint</div>
        <div class="fingerprint-words" style="font-size: 1.15rem; letter-spacing: normal;">Genesis Session — Awaiting Block #1</div>
        <div class="fingerprint-subtitle">ആദ്യത്തെ ഇടപാട് രേഖപ്പെടുത്തുമ്പോൾ ക്രിപ്റ്റോഗ്രാഫിക് കോഡ് ഇവിടെ തെളിയും</div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div class="fingerprint-card">
        <div class="fingerprint-title">🔐 ഇന്നത്തെ യോഗ കോഡ് | 6-Word Spoken Meeting Fingerprint</div>
        <div class="fingerprint-words">{fingerprint_ml}</div>
        <div class="fingerprint-subtitle">({fingerprint_en})</div>
        <div style="font-size:0.82rem; color:#FEF3C7; opacity:0.95; margin-top:6px;">
            സെക്രട്ടറിയും അംഗങ്ങളും യോഗം അവസാനിപ്പിക്കുമ്പോൾ ഉറക്കെ ചൊല്ലി ഉറപ്പുവരുത്തുക
        </div>
    </div>
    """, unsafe_allow_html=True)

    fp_cache_key = f"fp_audio_{latest_hash}"
    if st.button("🔊 യോഗ കോഡ് കേൾക്കുക | Speak Meeting Code", use_container_width=True):
        try:
            fp_tts = gTTS(text=fingerprint_spoken, lang="ml")
            fp_buf = io.BytesIO()
            fp_tts.write_to_fp(fp_buf)
            st.session_state[fp_cache_key] = fp_buf.getvalue()
        except Exception as e:
            st.caption(f"Audio fallback: {fingerprint_spoken}")

    if st.session_state.get(fp_cache_key):
        st.audio(st.session_state[fp_cache_key], format="audio/mp3", autoplay=True)

# ==============================================================================
# 3 Calm, Full-Width Tabs (Record & Confirm, Passbook & Balances, Security Check)
# ==============================================================================
tab1, tab2, tab3 = st.tabs([
    "🎙️ കണക്ക് ചേർക്കുക (Record & Confirm)",
    "📖 പാസ്ബുക്കും ബാക്കിപത്രവും (Passbook & Balances)",
    "🛡️ സുരക്ഷാ പരിശോധന (Security & Audit Check)"
])

# ==============================================================================
# TAB 1: Record & Confirm Spoken Voice Entry
# ==============================================================================
with tab1:
    with st.container(border=True):

        # Prominent receipt card if previous transaction was committed
        if st.session_state.get("last_commit_receipt"):
            st.success(
                f"{st.session_state['last_commit_receipt']}\n\n"
                "📖 **പാസ്ബുക്ക് ടാബിൽ വിവരങ്ങൾ കാണാം (View in Passbook tab)**"
            )
            if st.button("➕ അടുത്ത ഇടപാട് ചേർക്കുക | Record Next Transaction", type="primary", use_container_width=True, key="btn_next_tx_top"):
                st.session_state["last_commit_receipt"] = None
                st.session_state["stt_result"] = None
                st.session_state["current_audio_bytes"] = None
                st.session_state["current_clip_hash"] = None
                st.session_state["audio_input_counter"] = st.session_state.get("audio_input_counter", 0) + 1
                st.rerun()
            st.markdown("---")

        st.markdown('<div class="section-title">🎙️ സംസാരിച്ച് കണക്ക് ചേർക്കുക | Speak & Record Entry</div>', unsafe_allow_html=True)
        st.caption("അംഗത്തിന്റെ പേരും തുകയും ഇടപാടും പറയുക (ഉദാ: 'ലീല 100 രൂപ സമ്പാദ്യം')")

        # Friendly Audio Input Selection
        audio_source = st.radio(
            "ശബ്ദം രേഖപ്പെടുത്തുന്ന രീതി (Audio Input Method):",
            ["🎙️ മൈക്കിൽ സംസാരിക്കുക (Live Microphone)", "🔊 മാതൃകാ ശബ്ദം കേൾക്കുക (Sample Voice Scenarios)", "📁 ഓഡിയോ ഫയൽ നൽകുക (Upload File)"],
            horizontal=True
        )

        audio_bytes = None

        if audio_source == "🎙️ മൈക്കിൽ സംസാരിക്കുക (Live Microphone)":
            mic_audio = st.audio_input(
                "മൈക്ക് ഓൺ ചെയ്ത് ഇടപാട് പറയുക:",
                key=f"tx_mic_input_{st.session_state.get('audio_input_counter', 0)}"
            )
            if mic_audio is not None:
                audio_bytes = mic_audio.read()
                st.session_state["current_audio_bytes"] = audio_bytes
                st.session_state["current_clip_hash"] = hashlib.sha256(audio_bytes).hexdigest()
                st.session_state["last_commit_receipt"] = None

        elif audio_source == "📁 ഓഡിയോ ഫയൽ നൽകുക (Upload File)":
            uploaded_file = st.file_uploader(
                "ഓഡിയോ ഫയൽ തിരഞ്ഞെടുക്കുക (WAV / MP3, <= 30 സെക്കൻഡ്)",
                type=["wav", "mp3"],
                key=f"tx_file_uploader_{st.session_state.get('audio_input_counter', 0)}"
            )
            if uploaded_file is not None:
                audio_bytes = uploaded_file.read()
                st.session_state["current_audio_bytes"] = audio_bytes
                st.session_state["current_clip_hash"] = hashlib.sha256(audio_bytes).hexdigest()
                st.session_state["last_commit_receipt"] = None

        else:
            sample_scenarios = {
                "1. ലീല — 100 രൂപ സമ്പാദ്യം (Leela 100 roopa thrift)": "Leela 100 roopa thrift",
                "2. രാധ — 1000 രൂപ വായ്പ (Radha 1000 roopa loan vaaypa)": "Radha 1000 roopa loan vaaypa",
                "3. ചിത്ര — 50 രൂപ പിഴ (Chitra 50 roopa pizha adachu)": "Chitra 50 roopa pizha adachu",
                "4. മീര — 500 രൂപ തിരിച്ചടവ് (Meera 500 roopa repayment adachu)": "Meera 500 roopa repayment adachu",
                "5. രാധ — 500 രൂപ വായ്പ തിരിച്ചടച്ചു (Radha 500 roopa vaaypa adachu)": "Radha 500 roopa vaaypa adachu"
            }
            chosen_scenario = st.selectbox("മാതൃകാ ഇടപാട് തിരഞ്ഞെടുക്കുക (Select Scenario):", list(sample_scenarios.keys()))
            spoken_text = sample_scenarios[chosen_scenario]

            if st.button("🔊 മാതൃകാ ശബ്ദം ഉണ്ടാക്കുക (Synthesize with gTTS)", use_container_width=True):
                with st.spinner(f"ശബ്ദം തയ്യാറാക്കുന്നു: '{spoken_text}'..."):
                    try:
                        audio_bytes = synthesize_spoken_scenario(spoken_text)
                        st.session_state["sample_text"] = spoken_text
                        st.session_state["current_audio_bytes"] = audio_bytes
                        st.session_state["current_clip_hash"] = hashlib.sha256(audio_bytes).hexdigest()
                        st.session_state["stt_result"] = None
                        st.session_state["last_commit_receipt"] = None
                    except Exception as e:
                        st.error(f"ശബ്ദം ഉണ്ടാക്കുന്നതിൽ പിശക്: {e}")

        # Audio Playback
        if st.session_state.get("current_audio_bytes"):
            cur_bytes = st.session_state["current_audio_bytes"]
            is_mp3 = cur_bytes.startswith(b"ID3") or cur_bytes[:2] in [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"]
            fmt = "audio/mp3" if is_mp3 else "audio/wav"

            st.audio(cur_bytes, format=fmt)

            # Audio Hash for Judges: Closed by default
            clip_hash = st.session_state["current_clip_hash"]
            with st.expander("🔍 ശബ്ദ ഫയലിന്റെ ഡിജിറ്റൽ വിരലടയാളം | Audio Hash (For Judges)", expanded=False):
                st.code(clip_hash, language="text")
                st.caption(f"Audio Size: {len(cur_bytes)} bytes | Format: {fmt}")

            # Button: Process Audio with Gnani Prisma
            if st.button("🚀 സംസാരിച്ചത് പരിശോധിക്കുക | Process with Gnani Prisma v3.0", type="primary", use_container_width=True):
                with st.spinner("ജ്ഞാനി എഐ (Gnani AI) ശബ്ദം തിരിച്ചറിയുന്നു..."):
                    result = process_voice_entry(cur_bytes, member_names)

                    # Fallback to local parser if Gnani returned empty due to network connectivity
                    if not result.get("transcript_pass1") and "sample_text" in st.session_state:
                        text = st.session_state["sample_text"]
                        amt = normalize_amount(text)
                        matched_m, m_score = match_member_from_roster(text, text, member_names)
                        ev_type = detect_event_type(text)

                        reasons = []
                        if amt == 0.0:
                            reasons.append("തുക വ്യക്തമല്ല (Zero or undetectable amount in transcript).")
                        if matched_m == "Unknown":
                            reasons.append("അംഗത്തിന്റെ പേര് പട്ടികയിൽ വ്യക്തമായി തിരിച്ചറിഞ്ഞില്ല — ദയവായി താഴെ നിന്ന് ശരിയായ പേര് തിരഞ്ഞെടുക്കുക (Could not confidently match spoken name to the group roster — please verify the selected member below).")
                        if ev_type == "loan_disbursement":
                            reasons.append("സുരക്ഷാ പരിശോധന: വായ്പാ ഇടപാടുകൾ ഉറപ്പാക്കാൻ രണ്ട് പേരുടെ അനുമതി വേണം (High-risk transaction: Loan disbursements require roll-call scrutiny).")

                        status = "amber" if reasons else "green"
                        result = {
                            "status": status,
                            "matched_member": matched_m,
                            "member_confidence": m_score,
                            "event_type": ev_type,
                            "amount": amt,
                            "amt1": amt,
                            "amt2": amt,
                            "transcript_pass1": text,
                            "transcript_pass2": text,
                            "reasons": reasons
                        }

                    # Ensure Pass 2 fallback if Pass 2 was empty but Pass 1 has text
                    if result.get("transcript_pass1") and not result.get("transcript_pass2"):
                        result["transcript_pass2"] = result["transcript_pass1"]
                        result["amt2"] = result["amt1"]

                    st.session_state["stt_result"] = result

        # Review Card: Confirm Spoken Entry
        if st.session_state.get("stt_result"):
            res = st.session_state["stt_result"]
            st.markdown("---")
            st.markdown('<div class="section-title">📋 വിവരങ്ങൾ ഉറപ്പുവരുത്തുക | Confirm Spoken Entry</div>', unsafe_allow_html=True)

            # Bilingual Green / Amber Status Badges
            if res["status"] == "green":
                st.markdown('<div class="badge-green">🟢 ശരിയായി രേഖപ്പെടുത്തി | VERIFIED & CONSISTENT (Green)</div>', unsafe_allow_html=True)
                st.caption("ശബ്ദം വ്യക്തമായി തിരിച്ചറിഞ്ഞു. സംശയങ്ങളൊന്നുമില്ല (Dual-pass STT matched cleanly).")
            else:
                st.markdown('<div class="badge-amber">🟠 പരിശോധന ആവശ്യമാണ് | REVIEW REQUIRED (Amber)</div>', unsafe_allow_html=True)
                for r in res.get("reasons", []):
                    warn_text = r if r.startswith("⚠️") else f"⚠️ {r}"
                    st.warning(warn_text)

            # Progressive Disclosure: Technical Transcripts for Hackathon Judges (Closed by default)
            with st.expander("🔍 സാങ്കേതിക വിവരങ്ങൾ | Dual-Pass STT Technical Audit (For Judges)", expanded=False):
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    st.markdown("**Pass 1: Inverse Text Normalization (മലയാളം)**")
                    st.code(res.get("transcript_pass1", "(empty)"), language="text")
                    st.caption(f"തിരിച്ചറിഞ്ഞ തുക (Amt 1): ₹{res.get('amt1', 0.0):.2f}")
                with col_t2:
                    st.markdown("**Pass 2: Transliteration (Latin Phonetic)**")
                    p2_tx = res.get("transcript_pass2") or res.get("transcript_pass1") or "(empty)"
                    st.code(p2_tx, language="text")
                    st.caption(f"തിരിച്ചറിഞ്ഞ തുക (Amt 2): ₹{res.get('amt2', res.get('amt1', 0.0)):.2f}")
                st.caption(f"Roster Match Score: {res.get('member_confidence', 0.0):.1f}%")

            # Editable fields with friendly Malayalam + English labels
            # Prevent false defaulting to index=0 when speech cannot be matched confidently
            is_member_matched = (
                res.get("matched_member") in member_names and
                res.get("member_confidence", 0) > 60
            )

            if is_member_matched:
                selected_member = st.selectbox(
                    "അംഗത്തിന്റെ പേര് (Member Transacting):",
                    member_names,
                    index=member_names.index(res["matched_member"]),
                    key="sel_transacting_member"
                )
            else:
                member_options = ["-- അംഗത്തെ തിരഞ്ഞെടുക്കുക (Select Member) --"] + member_names
                selected_member = st.selectbox(
                    "അംഗത്തിന്റെ പേര് (Member Transacting):",
                    member_options,
                    index=0,
                    key="sel_transacting_member"
                )
                if selected_member == "-- അംഗത്തെ തിരഞ്ഞെടുക്കുക (Select Member) --":
                    st.caption("ℹ️ ദയവായി ഇടപാട് നടത്തിയ അംഗത്തിന്റെ പേര് മുകളിലെ പട്ടികയിൽ നിന്ന് തിരഞ്ഞെടുക്കുക.")

            # ── Live Member Savings / Loan Status Badge ──────────────────────
            if selected_member in member_names:
                _balances = calculate_derived_balances(meeting_id)
                _m_data = _balances.get("members", {}).get(selected_member, {})
                _savings = float(_m_data.get("savings", 0.0))
                _debt = float(_m_data.get("debt", 0.0))
                _savings_color = "#2d7a2d" if _savings > 0 else "#888"
                _debt_color = "#b22222" if _debt > 0 else "#888"
                st.markdown(
                    f'<p style="font-size:0.82rem; margin:2px 0 8px 0;">'
                    f'💡 നിലവിലെ സമ്പാദ്യം (Savings): '
                    f'<strong style="color:{_savings_color};">₹{_savings:.2f}</strong>'
                    f'&nbsp;&nbsp;|&nbsp;&nbsp;'
                    f'നിലവിലെ വായ്പ (Outstanding Debt): '
                    f'<strong style="color:{_debt_color};">₹{_debt:.2f}</strong>'
                    f'</p>',
                    unsafe_allow_html=True
                )

            event_options = ["thrift", "loan_disbursement", "repayment", "fine"]
            ev_default = res["event_type"] if res["event_type"] in event_options else "thrift"
            ev_idx = event_options.index(ev_default)
            selected_event = st.selectbox(
                "ഇടപാട് തരം (Transaction Type):",
                event_options,
                index=ev_idx,
                format_func=lambda x: EVENT_LABELS.get(x, x),
                key="sel_trans_type"
            )

            # Preserve user-edited amount across rerenders:
            # Only fall back to STT-detected amount when the widget hasn't been touched yet.
            _stt_amount = float(res.get("amount", 0.0))
            _current_amount = float(st.session_state.get("num_trans_amount", _stt_amount))
            selected_amount = st.number_input(
                "തുക (Amount in ₹):",
                min_value=0.0,
                value=_current_amount,
                step=50.0,
                format="%.2f",
                key="num_trans_amount"
            )

            # Roll-call confirmation dropdown: prefer officer who is not the transacting member
            confirmed_by_names = [f"{m['name']} — {ROLE_LABELS.get(m['role'], m['role'])}" for m in members]
            confirmed_by_idx = 0
            for i, m in enumerate(members):
                if m["name"] == selected_member:
                    continue
                if m["role"] in ["secretary", "president"]:
                    confirmed_by_idx = i
                    break

            selected_confirmed_by_label = st.selectbox(
                "സ്ഥിരീകരിച്ച ഭാരവാഹി (Roll-call Confirmed By):",
                confirmed_by_names,
                index=confirmed_by_idx,
                key="sel_confirmed_by"
            )
            confirmed_by_member_obj = members[confirmed_by_names.index(selected_confirmed_by_label)]
            confirmed_by_name = confirmed_by_member_obj["name"]
            confirmed_by_id = confirmed_by_member_obj["id"]
            confirmed_by_role = confirmed_by_member_obj["role"]

            # Logical Accounting & Governance Rules Validation
            if selected_member == "-- അംഗത്തെ തിരഞ്ഞെടുക്കുക (Select Member) --" or selected_member not in member_names:
                is_tx_valid = False
                tx_validation_err = "⚠️ ദയവായി ഇടപാട് നടത്തിയ അംഗത്തിന്റെ പേര് മുകളിൽ നിന്ന് തിരഞ്ഞെടുക്കുക (Please select the transacting member from the dropdown above)."
            else:
                is_tx_valid, tx_validation_err = validate_transaction_logic(
                    meeting_id=meeting_id,
                    member_name=selected_member,
                    event_type=selected_event,
                    amount=selected_amount,
                    confirmed_by_name=confirmed_by_name,
                    confirmed_by_role=confirmed_by_role
                )

            if not is_tx_valid:
                st.warning(tx_validation_err)

            # Audible Pure Malayalam Read-Back Player (Clean without English codes)
            if selected_member in member_names:
                st.markdown("🔊 **ശബ്ദത്തിൽ കേട്ട് ഉറപ്പുവരുത്തുക (Audible Read-Back):**")
                readback_bytes = generate_readback_audio(selected_member, selected_event, selected_amount)
                if readback_bytes:
                    st.audio(readback_bytes, format="audio/mp3")
                    amt_disp = f"{int(selected_amount)}" if selected_amount.is_integer() else f"{selected_amount:.2f}"
                    pure_event_str = EVENT_PURE_ML.get(selected_event, "ഇടപാട്")
                    st.caption(f'📢 *"{selected_member}, {pure_event_str}, {amt_disp} രൂപ. ഇത് ശരിയാണോ?"*')
            if readback_bytes:
                st.audio(readback_bytes, format="audio/mp3")
                amt_disp = f"{int(selected_amount)}" if selected_amount.is_integer() else f"{selected_amount:.2f}"
                pure_event_str = EVENT_PURE_ML.get(selected_event, "ഇടപാട്")
                st.caption(f'📢 *"{selected_member}, {pure_event_str}, {amt_disp} രൂപ. ഇത് ശരിയാണോ?"*')

            # Big Accessible Confirm & Sign Button
            confirm_help = tx_validation_err if not is_tx_valid else "ഇടപാട് സ്ഥിരീകരിച്ച് പാസ്ബുക്കിൽ ചേർക്കുക"
            submit_confirm = st.button(
                "🔒 ഒപ്പിട്ട് പാസ്ബുക്കിൽ ചേർക്കുക | Confirm & Append to Hash Chain",
                type="primary",
                use_container_width=True,
                disabled=(not is_tx_valid),
                help=confirm_help
            )

            if submit_confirm and is_tx_valid:
                clip_hash = st.session_state["current_clip_hash"]
                audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio", "clips")
                os.makedirs(audio_dir, exist_ok=True)

                saved_bytes = st.session_state["current_audio_bytes"]
                ext = "mp3" if (saved_bytes.startswith(b"ID3") or saved_bytes[:2] in [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"]) else "wav"
                file_name = f"{clip_hash[:8]}.{ext}"
                file_path = os.path.join("audio", "clips", file_name)
                full_save_path = os.path.join(audio_dir, file_name)

                with open(full_save_path, "wb") as f:
                    f.write(saved_bytes)

                conn = get_db_connection(DB_PATH)
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO audio_clips (meeting_id, file_path, clip_hash) VALUES (?, ?, ?);",
                    (meeting_id, file_path, clip_hash)
                )
                clip_id = cur.lastrowid
                conn.commit()
                conn.close()

                mem_id = member_dict[selected_member]
                entry_id = add_ledger_entry(
                    meeting_id=meeting_id,
                    member_id=mem_id,
                    clip_id=clip_id,
                    event_type=selected_event,
                    amount=selected_amount,
                    confirmed_by=confirmed_by_id,
                    clip_hash=clip_hash
                )

                # Clear active review card state and audio buffers
                st.session_state["stt_result"] = None
                st.session_state["current_audio_bytes"] = None
                st.session_state["current_clip_hash"] = None
                st.session_state["verification_result"] = None
                st.session_state.pop("sample_text", None)
                st.session_state["audio_input_counter"] = st.session_state.get("audio_input_counter", 0) + 1

                # Store receipt message for the top of Tab 1
                st.session_state["last_commit_receipt"] = f"✅ രേഖപ്പെടുത്തി! (Saved to Passbook): {selected_member} — ₹{selected_amount:.2f} (Block #{entry_id})"
                st.toast(f"ഇടപാട് #{entry_id} വിജയകരമായി ഒപ്പിട്ട് പാസ്ബുക്കിൽ ചേർത്തു!", icon="✅")
                st.rerun()


# ==============================================================================
# TAB 2: Full-Width Passbook, Balances & Evidence Audio Inspector
# ==============================================================================
with tab2:
    with st.container(border=True):
        st.markdown('<div class="section-title">📖 അയൽക്കൂട്ടം പാസ്ബുക്കും ബാക്കിപത്രവും | Passbook & Balances</div>', unsafe_allow_html=True)
        st.caption("യോഗത്തിലെ എല്ലാ സമ്പാദ്യങ്ങളും വായ്പകളും സുരക്ഷിതമായി ഇവിടെ രേഖപ്പെടുത്തിയിരിക്കുന്നു:")

        # 4 Full-Width Summary Metrics (Plenty of horizontal room, zero ₹0.... truncation)
        balances_data = calculate_derived_balances(meeting_id)
        summary = balances_data["summary"]

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("സമ്പാദ്യം (Savings)", f"₹{summary['total_savings']:.2f}")
        col_m2.metric("വായ്പ (Loans)", f"₹{summary['total_disbursed']:.2f}")
        col_m3.metric("തിരിച്ചടവ് (Repaid)", f"₹{summary['total_repaid']:.2f}")
        col_m4.metric("ബാക്കി (Net Debt)", f"₹{summary['total_outstanding_debt']:.2f}")

        st.markdown("---")
        st.markdown('<div class="section-title">👥 അംഗങ്ങളുടെ ബാക്കിപത്രം (Member Balances Breakdown)</div>', unsafe_allow_html=True)

        member_bal_list = []
        for m_name, d in balances_data["members"].items():
            member_bal_list.append({
                "അംഗം (Member)": m_name,
                "ചുമതല (Role)": ROLE_LABELS.get(d["role"], d["role"]),
                "സമ്പാദ്യം (Savings)": f"₹{d['savings']:.2f}",
                "വായ്പ (Disbursed)": f"₹{d['loan_disbursed']:.2f}",
                "തിരിച്ചടച്ചത് (Repaid)": f"₹{d['repaid']:.2f}",
                "ബാക്കി വായ്പ (Debt)": f"₹{d['debt']:.2f}",
                "പിഴ (Fines)": f"₹{d['fines']:.2f}"
            })

        st.dataframe(pd.DataFrame(member_bal_list), use_container_width=True, hide_index=True)

        st.markdown("---")
        col_hdr, col_undo = st.columns([1.6, 1.4])
        with col_hdr:
            st.markdown('<div class="section-title">📜 രേഖപ്പെടുത്തിയ ഇടപാടുകൾ (Committed Ledger Blocks)</div>', unsafe_allow_html=True)
        with col_undo:
            if st.button("↩️ അവസാന ഇടപാട് മാറ്റുക | Undo Last", key="btn_undo_tab2", use_container_width=True):
                undo_res = delete_latest_ledger_entry(meeting_id)
                if undo_res["success"]:
                    st.toast(f"ഇടപാട് #{undo_res['deleted_entry_id']} ഒഴിവാക്കി!", icon="🗑️")
                    st.session_state["verification_result"] = None
                    st.rerun()
                else:
                    st.toast(undo_res.get("error", "ഒഴിവാക്കാൻ ഇടപാടുകളൊന്നുമില്ല"), icon="⚠️")

        # Fetch current ledger entries for this meeting
        conn = get_db_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                le.id, m.name as member, le.event_type, le.amount, 
                cb.name as confirmed_by,
                SUBSTR(ac.clip_hash, 1, 8) as clip_hash,
                SUBSTR(le.prev_hash, 1, 8) as prev_hash,
                SUBSTR(le.entry_hash, 1, 12) as entry_hash,
                le.timestamp
            FROM ledger_entries le
            JOIN members m ON le.member_id = m.id
            JOIN members cb ON le.confirmed_by = cb.id
            JOIN audio_clips ac ON le.clip_id = ac.id
            WHERE le.meeting_id = ?
            ORDER BY le.id ASC;
        """, (meeting_id,))
        rows = cur.fetchall()
        conn.close()

        if rows:
            display_data = []
            for idx, r in enumerate(rows, start=1):
                display_data.append({
                    "നമ്പർ (ID)": idx,
                    "അംഗം (Member)": r["member"],
                    "ഇടപാട് (Type)": EVENT_LABELS.get(r["event_type"], r["event_type"]),
                    "തുക (Amount)": r["amount"],
                    "സ്ഥിരീകരിച്ചത് (Confirmed By)": r["confirmed_by"],
                    "ശബ്ദ കോഡ് (Audio Hash)": r["clip_hash"],
                    "തീയതി (Time)": r["timestamp"].split("T")[-1][:5] if "T" in r["timestamp"] else r["timestamp"][-8:],
                    "_entry_hash": r["entry_hash"],
                    "_db_id": r["id"]
                })

            df = pd.DataFrame(display_data)
            st.dataframe(
                df.drop(columns=["_entry_hash", "_db_id"]),
                column_config={
                    "നമ്പർ (ID)": st.column_config.NumberColumn("നമ്പർ", format="%d", width="small"),
                    "അംഗം (Member)": st.column_config.TextColumn("അംഗം", width="medium"),
                    "ഇടപാട് (Type)": st.column_config.TextColumn("ഇടപാട്", width="large"),
                    "തുക (Amount)": st.column_config.NumberColumn("തുക (₹)", format="₹%.2f"),
                    "സ്ഥിരീകരിച്ചത് (Confirmed By)": st.column_config.TextColumn("ഒപ്പിട്ടത്"),
                    "ശബ്ദ കോഡ് (Audio Hash)": st.column_config.TextColumn("ഓഡിയോ"),
                    "തീയതി (Time)": st.column_config.TextColumn("സമയം")
                },
                use_container_width=True,
                hide_index=True
            )

            st.markdown("---")
            # Evidence Audio Clip Inspector
            st.markdown('<div class="section-title">🎧 രേഖപ്പെടുത്തിയ ശബ്ദം കേൾക്കുക | Inspect Evidence Audio Clip</div>', unsafe_allow_html=True)
            conn = get_db_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    le.id, m.name as member, le.event_type, le.amount, 
                    ac.file_path, ac.clip_hash, le.timestamp
                FROM ledger_entries le
                JOIN members m ON le.member_id = m.id
                JOIN audio_clips ac ON le.clip_id = ac.id
                WHERE le.meeting_id = ?
                ORDER BY le.id ASC;
            """, (meeting_id,))
            audio_entry_rows = cur.fetchall()
            conn.close()

            entry_labels = [
                f"ഇടപാട് #{idx} — {r['member']} ({EVENT_LABELS.get(r['event_type'], r['event_type'])}, ₹{r['amount']:.2f})"
                for idx, r in enumerate(audio_entry_rows, start=1)
            ]
            selected_label = st.selectbox("കേൾക്കേണ്ട ഇടപാട് തിരഞ്ഞെടുക്കുക (Select Entry to Audit):", entry_labels)
            selected_entry_idx = entry_labels.index(selected_label)
            selected_row = audio_entry_rows[selected_entry_idx]

            col_ev1, col_ev2 = st.columns([3, 2])
            with col_ev1:
                st.markdown(f"**ഇടപാട് നമ്പർ:** `#{selected_entry_idx + 1}` &nbsp;|&nbsp; **അംഗം:** `{selected_row['member']}` &nbsp;|&nbsp; **തുക:** `₹{selected_row['amount']:.2f}`")
                with st.expander("🔍 പൂർണ്ണ ഓഡിയോ ഹാഷ് | Full SHA-256 Hash (For Judges)", expanded=False):
                    st.code(selected_row['clip_hash'], language="text")
                    st.caption(f"Time: {selected_row['timestamp']} | Path: {selected_row['file_path']}")
            with col_ev2:
                clip_path = selected_row["file_path"]
                abs_clip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), clip_path)
                if os.path.exists(abs_clip_path):
                    with open(abs_clip_path, "rb") as af:
                        clip_bytes = af.read()
                    fmt = "audio/mp3" if clip_path.endswith(".mp3") else "audio/wav"
                    st.audio(clip_bytes, format=fmt)
                else:
                    st.warning(f"ഓഡിയോ ഫയൽ '{clip_path}' കണ്ടെത്താനായില്ല.")

        else:
            st.info("ഈ യോഗത്തിൽ ഇതുവരെ ഇടപാടുകളൊന്നും രേഖപ്പെടുത്തിയിട്ടില്ല. ആദ്യത്തെ ടാബിൽ നിന്ന് ശബ്ദം നൽകി ബ്ലോക്ക് #1 രേഖപ്പെടുത്തുക. (No ledger entries yet).")


# ==============================================================================
# TAB 3: Security & Cryptographic Audit Check
# ==============================================================================
with tab3:
    with st.container(border=True):
        st.markdown('<div class="section-title">🛡️ സുരക്ഷാ പരിശോധന | Security & Audit Check</div>', unsafe_allow_html=True)
        st.caption("ക്രിപ്റ്റോഗ്രാഫിക് ഹാഷ് ചെയിനും യോഗ കോഡും പരിശോധിച്ച് കണക്കുകൾ സുരക്ഷിതമാണെന്ന് ഉറപ്പാക്കാം:")

        # Detailed Meeting Fingerprint Section
        st.markdown("#### 🔐 6-വാക്ക് യോഗ കോഡ് (Meeting Voice Fingerprint)")
        st.markdown(f"""
        <div class="fingerprint-card">
            <div class="fingerprint-title">ഇന്നത്തെ യോഗ കോഡ് | Current Session Fingerprint</div>
            <div class="fingerprint-words">{fingerprint_ml}</div>
            <div class="fingerprint-subtitle">({fingerprint_en})</div>
            <div style="font-size:0.85rem; color:#FEF3C7; opacity:0.95; margin-top:8px; line-height:1.5;">
                💡 <b>എന്താണ് യോഗ കോഡ്?</b> യോഗം പിരിയുമ്പോൾ സെക്രട്ടറി ഈ 6 വാക്കുകൾ ഉറക്കെ വായിക്കുകയും അംഗങ്ങൾ തങ്ങളുടെ ഫോണിലെ പാസ്ബുക്കുമായി ഒത്തുനോക്കുകയും ചെയ്യുന്നു. ഇതിൽ ഒരു പൈസയുടെ മാറ്റം ആരെങ്കിലും വരുത്തിയാൽ ഈ 6 വാക്കുകൾ പൂർണ്ണമായി മാറും!
            </div>
        </div>
        """, unsafe_allow_html=True)

        if fingerprint_ml != "Genesis Session — Awaiting Block #1":
            tab3_fp_key = f"tab3_fp_audio_{latest_hash}"
            if st.button("🔊 യോഗ കോഡ് ഉച്ചത്തിൽ കേൾക്കുക | Speak Fingerprint Out Loud", use_container_width=True):
                try:
                    fp_tts = gTTS(text=fingerprint_spoken, lang="ml")
                    fp_buf = io.BytesIO()
                    fp_tts.write_to_fp(fp_buf)
                    st.session_state[tab3_fp_key] = fp_buf.getvalue()
                except Exception as e:
                    st.caption(f"Audio fallback: {fingerprint_spoken}")

            if st.session_state.get(tab3_fp_key):
                st.audio(st.session_state[tab3_fp_key], format="audio/mp3", autoplay=True)

        st.markdown("---")
        st.markdown('<div class="section-title">🔍 ക്രിപ്റ്റോഗ്രാഫിക് ചെയിൻ സമഗ്ര പരിശോധന (Chain Integrity Verification)</div>', unsafe_allow_html=True)
        st.caption("ഡാറ്റാബേസിലെ ഓരോ ബ്ലോക്കിന്റെയും SHA-256 ഹാഷും മുൻ ബ്ലോക്കുമായുള്ള ബന്ധവും ശബ്ദ രേഖയും സാധുത പരിശോധിക്കുക:")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔍 കണക്കുകൾ പരിശോധിച്ച് ഉറപ്പാക്കുക | Verify Ledger Integrity", use_container_width=True, type="primary"):
                st.session_state["verification_result"] = verify_chain(meeting_id)

        with col_btn2:
            if st.button("⚠️ കൃത്രിമം കാണിച്ചു നോക്കുക (+₹500) | Simulate Tamper", use_container_width=True):
                conn = get_db_connection(DB_PATH)
                cur = conn.cursor()
                cur.execute("""
                    UPDATE ledger_entries 
                    SET amount = amount + 500.0 
                    WHERE id = (
                        SELECT id FROM ledger_entries WHERE meeting_id = ? ORDER BY id DESC LIMIT 1
                    );
                """, (meeting_id,))
                conn.commit()
                changes = conn.total_changes
                conn.close()
                if changes > 0:
                    st.session_state["verification_result"] = verify_chain(meeting_id)
                    st.toast("⚠️ തുകയിൽ അനധികൃതമായി ₹500 കൂട്ടി കൃത്രിമം കാണിച്ചു!", icon="⚠️")
                    st.rerun()
                else:
                    st.warning("ആദ്യം പാസ്ബുക്കിൽ ഒരു ഇടപാടെങ്കിലും ചേർക്കുക!")

        # Verification Result Callout
        if st.session_state.get("verification_result") is not None:
            v_res = st.session_state["verification_result"]
            if v_res.get("valid"):
                st.success("✅ **കണക്കുകൾ തികച്ചും സുരക്ഷിതമാണ് (Ledger Intact)**: പാസ്ബുക്കിലെ എല്ലാ ക്രിപ്റ്റോഗ്രാഫിക് ചെയിൻ കണ്ണികളും ശബ്ദ രേഖകളും 100% ഒത്തുപോകുന്നു. മാറ്റങ്ങളൊന്നും സംഭവിച്ചിട്ടില്ല.")
            else:
                st.error(f"""
                🚨 **കണക്കിൽ കൃത്രിമം കണ്ടെത്തി! (TAMPER DETECTED)**
            
                **തകർക്കപ്പെട്ട ഇടപാട്:** Block #{v_res.get('broken_at_entry_id')} ({v_res.get('member')})  
                **കാരണം:** {v_res.get('reason')}
            
                *ഗണിതശാസ്ത്രപരമായ SHA-256 ഹാഷ് ശൃംഖല തകർന്നിരിക്കുന്നു. ആരെങ്കിലും ഡാറ്റാബേസിൽ അനധികൃതമായി മാറ്റം വരുത്തിയതായി സിസ്റ്റം കണ്ടെത്തി!*
                """)

        st.markdown("---")
        st.markdown('<div class="section-title">🏛️ സാങ്കേതിക വാസ്തുവിദ്യ (Technical Architecture for Judges)</div>', unsafe_allow_html=True)
        st.markdown("""
        - **ശൃംഖലാ സമവാക്യം (Hash Formula):**  
          `Entry_Hash = SHA256(prev_hash | meeting_id | member_id | clip_hash | event_type | amount | confirmed_by | timestamp)`
        - **ശബ്ദ തെളിവ് (Voice Binding):**  
          ഓരോ ഇടപാടും അതിൽ സംസാരിച്ച ഓഡിയോ ഫയലിന്റെ യഥാർത്ഥ `clip_hash = SHA256(audio_bytes)` മായി ക്രിപ്റ്റോഗ്രാഫിക്കലായി ബന്ധിപ്പിച്ചിരിക്കുന്നു.
        - **യോഗ വിരലടയാളം (6-Word Fingerprint):**  
          ഏറ്റവും പുതിയ ബ്ലോക്കിന്റെ ആദ്യത്തെ 15 ഹെക്സ് അക്ഷരങ്ങളെ 32 മലയാള പദങ്ങളുടെ നിഘണ്ടുവിലേക്ക് മാപ്പ് ചെയ്ത് ഉണ്ടാക്കുന്ന 6 വാക്കുകൾ.
        """)

# ==============================================================================
# Footer
# ==============================================================================
st.markdown("---")
st.caption("നിധി ഫ്ലോ — കമ്മ്യൂണിറ്റി ശബ്ദ പാസ്ബുക്ക് | Gnani.ai Prisma v3.0 STT + SHA-256 Hash Chaining | Tamper-Evident Community Microfinance Companion")
