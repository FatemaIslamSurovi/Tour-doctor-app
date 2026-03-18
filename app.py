import os
import re
import json
from dataclasses import dataclass
from typing import Any, Dict

import streamlit as st
from openai import OpenAI

# -----------------------------
# Constants / Rules
# -----------------------------
BANNED_WORDS = ["360", "VR", "virtual", "virtual reality"]
BANNED_SYMBOLS = ["°"]

NOTE_EN_TEMPLATE = (
    "NOTE: Topics and multi-media content in this virtual tour may be sensitive for some viewers. "
    "If you are 13 years of age or younger, please ask an adult to preview this tour before you go any further.  {cw}"
)
NOTE_FR_TEMPLATE = (
    "REMARQUE : Les sujets et le contenu multimédia de cette visite virtuelle peuvent être sensibles pour certains spectateurs. "
    "Si vous avez 13 ans ou moins, veuillez demander à un adulte de prévisualiser cette visite avant d’aller plus loin. {cw}"
)

COLUMNS = [
    "TOUR NAME",
    "TOUR NAME FRENCH",
    "DESCRIPTION",
    "DESCRIPTION FRENCH",
    "URL",
    "LIVE CAMS",
    "TOUR CATEGORY ID",
    "TAGS (separated by commas)",
    "TAGS FR",
    "CURATOR NOTES",
]

# -----------------------------
# Helpers
# -----------------------------
def strip_banned(text: str) -> str:
    if not text:
        return ""
    t = text
    for sym in BANNED_SYMBOLS:
        t = t.replace(sym, "")
    for w in BANNED_WORDS:
        t = re.sub(rf"\b{re.escape(w)}\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def limit_sentences(text: str, max_sentences: int = 3) -> str:
    """Simple sentence limiter for EN/FR."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    parts = [p.strip() for p in parts if p.strip()]
    return " ".join(parts[:max_sentences])


def title_case_tags(tags: str) -> str:
    items = [x.strip() for x in (tags or "").split(",")]
    items = [x for x in items if x]
    # Title Case each tag (simple approach)
    items = [x.title() for x in items]
    return ", ".join(items)


def extract_json(text: str) -> Dict[str, Any]:
    """Robustly extract JSON object even if extra text appears."""
    t = (text or "").strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in model output.")
    return json.loads(m.group(0))


def ensure_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure required keys exist and are strings (except booleans/ints)."""
    defaults = {
        "tour_name_en": "",
        "tour_name_fr": "",
        "description_en": "",
        "description_fr": "",
        "url": "",
        "live_cams": "",
        "tour_category_id": "",
        "tags_en": "",
        "tags_fr": "",
        "curator_notes": "",
        "cw_required": False,
        "cw_label": "",
        "accuracy_score_0_100": 0,
        "confidence_reasons": [],
    }
    out = defaults | (data or {})
    # Normalize types
    out["cw_required"] = bool(out.get("cw_required", False))
    try:
        out["accuracy_score_0_100"] = int(out.get("accuracy_score_0_100", 0))
    except Exception:
        out["accuracy_score_0_100"] = 0
    if not isinstance(out.get("confidence_reasons"), list):
        out["confidence_reasons"] = []
    for k in [
        "tour_name_en","tour_name_fr","description_en","description_fr","url",
        "live_cams","tour_category_id","tags_en","tags_fr","curator_notes","cw_label"
    ]:
        out[k] = str(out.get(k, "") or "")
    return out


def post_process(data: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce your rules after model output."""
    d = ensure_keys(data)

    # Remove banned words/symbols everywhere
    d["tour_name_en"] = strip_banned(d["tour_name_en"])
    d["tour_name_fr"] = strip_banned(d["tour_name_fr"])
    d["description_en"] = strip_banned(d["description_en"])
    d["description_fr"] = strip_banned(d["description_fr"])
    d["tags_en"] = strip_banned(d["tags_en"])
    d["tags_fr"] = strip_banned(d["tags_fr"])
    d["curator_notes"] = strip_banned(d["curator_notes"])

    # Sentence limit (3 sentences; NOTE is appended only when CW is required)
    d["description_en"] = limit_sentences(d["description_en"], 3)
    d["description_fr"] = limit_sentences(d["description_fr"], 3)

    # Tags formatting
    d["tags_en"] = title_case_tags(d["tags_en"])
    d["tags_fr"] = title_case_tags(d["tags_fr"])

    # If CW required, append required NOTE/REMARQUE
    if d["cw_required"]:
        if not d["cw_label"].strip():
            d["cw_label"] = "CW: sensitive content"
        note_en = NOTE_EN_TEMPLATE.format(cw=d["cw_label"].strip())
        note_fr = NOTE_FR_TEMPLATE.format(cw=d["cw_label"].strip().replace("CW:", "CW :"))

        d["description_en"] = (d["description_en"].rstrip() + " " + note_en).strip()
        d["description_fr"] = (d["description_fr"].rstrip() + " " + note_fr).strip()

    return d


# -----------------------------
# Prompt (OpenAI-only, using pasted text as evidence)
# -----------------------------
SYSTEM_PROMPT = """
You are TOUR.Doctor, an AI assistant that normalizes and validates educational tour metadata for a K–12 audience.
You MUST use ONLY the user-provided text as evidence (you cannot open the URL).

Return ONLY valid JSON with these keys exactly:
tour_name_en, tour_name_fr, description_en, description_fr, url, live_cams, tour_category_id,
tags_en, tags_fr, curator_notes, cw_required, cw_label, accuracy_score_0_100, confidence_reasons

OUTPUT / QUALITY RULES:
- description_en: max 3 sentences (a 4th sentence allowed ONLY if navigation is required).
- description_fr: max 3 sentences (a 4th sentence allowed ONLY if navigation is required).
- Grade 6 reading level, written for all ages.
- Warm, clear, factual, concise. No filler language. No repeated adjectives.
- Vary opening sentence (do not always start with “Explore”).
- Include specific details people will see; include 3–6 concrete examples when possible.
- Avoid vague phrases like “see animals” or “view exhibits”.

STRICT PROHIBITIONS:
- Do NOT use the words: 360, VR, virtual, virtual reality
- Do NOT use the degree symbol °

TAGS:
- tags_en and tags_fr must have 8–12 comma-separated tags (aim ~10), Title Case.
- Avoid generic tags like “Virtual Tour”, “Museum Exhibit”, “Experience”, “Learning”.
- Do not repeat words already used in the description.

FRENCH:
- Natural, simple K-12 French. No English in French tags unless proper nouns.

CW CHECK:
- If sensitive themes exist (nudity, sexual content, violence/injury, hate symbols/extremism, drugs, self-harm),
  set cw_required=true and cw_label like “CW: nudity in artwork”.
- If not sensitive, cw_required=false and cw_label="".

ACCURACY:
- accuracy_score_0_100 must reflect how complete and reliable the user-provided evidence is.
- confidence_reasons must be 3–6 short bullet-style strings explaining the score (clarity, completeness, ambiguity).

IMPORTANT:
- If some fields are missing from the input, infer cautiously and lower accuracy.
- url should be the URL found in the input (or blank if none).
- live_cams can be blank unless the input clearly indicates live cameras.
- curator_notes: short internal note about any uncertainty or special handling.
"""


def call_openai(model_name: str, raw_text: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set. Set it and restart VS Code/terminal.")
    client = OpenAI(api_key=api_key)

    user_prompt = f"""
Here is a raw pasted tour record (may contain EN/FR titles, EN/FR descriptions, URL, category id, tags, etc).
Extract, clean, and rewrite to meet the rules.

RAW RECORD:
{raw_text}
"""

    resp = client.responses.create(
        model=model_name,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    data = extract_json(resp.output_text)
    return post_process(data)


# -----------------------------
# Streamlit UI (light green + white)
# -----------------------------
st.set_page_config(page_title="TOUR.Doctor", page_icon="🩺", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 1.6rem;}
.card {background:#ffffff;border:1px solid #e8f3ec;border-radius:16px;padding:18px;
       box-shadow:0 6px 18px rgba(0,0,0,0.06);}
.badge {display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;
        border:1px solid #cfe8d6;background:#e9f7ef;}
.small {color:#52606d;font-size:13px;}
hr {border:none;border-top:1px solid #e8f3ec;margin:16px 0;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown("## 🩺 TOUR.Doctor  <span class='badge'>OpenAI-only</span>", unsafe_allow_html=True)
st.markdown("<div class='small'>Paste a full tour record → normalize → EN/FR output + tags + CW + accuracy</div>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Settings")
    model_name = st.text_input("Model", value="gpt-4.1-mini")
    st.caption("If you get a model error, tell me the error text and I’ll adjust it.")
    st.divider()
    st.subheader("Human Review Policy")
    st.write("≥ 90: Quick skim (10–15 sec)")
    st.write("80–89: Light review")
    st.write("< 80: Full human review")

raw_text = st.text_area(
    "Paste full tour metadata (any order is OK):",
    height=220,
    placeholder="Example: English title, French title, English description, French description, URL, category ID, tags...",
)

col1, col2 = st.columns([1, 1])
with col1:
    run_btn = st.button("✨ Generate Clean Output", type="primary", use_container_width=True)
with col2:
    clear_btn = st.button("🧹 Clear", use_container_width=True)

if clear_btn:
    st.session_state.pop("result", None)
    st.experimental_rerun()

if run_btn:
    if not raw_text.strip():
        st.error("Please paste a tour record first.")
    else:
        with st.spinner("Generating EN/FR descriptions + tags + CW + accuracy..."):
            try:
                result = call_openai(model_name=model_name, raw_text=raw_text.strip())
                st.session_state["result"] = result
                st.success("Done.")
            except Exception as e:
                st.error(f"Generation failed: {repr(e)}")

res = st.session_state.get("result")

if res:
    st.markdown("<hr/>", unsafe_allow_html=True)

    # Copy/paste format (like your sheet)
    block = (
        "TOUR NAME\n" + res["tour_name_en"].strip() + "\n\n"
        "TOUR NAME FRENCH\n" + res["tour_name_fr"].strip() + "\n\n"
        "DESCRIPTION\n" + res["description_en"].strip() + "\n\n"
        "DESCRIPTION FRENCH\n" + res["description_fr"].strip() + "\n\n"
        "URL\n" + res["url"].strip() + "\n\n"
        "LIVE CAMS\n" + res["live_cams"].strip() + "\n\n"
        "TOUR CATEGORY ID\n" + res["tour_category_id"].strip() + "\n\n"
        "TAGS (separated by commas)\n" + res["tags_en"].strip() + "\n\n"
        "TAGS FR\n" + res["tags_fr"].strip() + "\n\n"
        "CURATOR NOTES\n" + res["curator_notes"].strip() + "\n"
    )

    st.subheader("Output (Copy/Paste)")
    st.text_area("Copy this:", value=block, height=360)

    # Table row output (CSV-ready)
    row = {
        "TOUR NAME": res["tour_name_en"],
        "TOUR NAME FRENCH": res["tour_name_fr"],
        "DESCRIPTION": res["description_en"],
        "DESCRIPTION FRENCH": res["description_fr"],
        "URL": res["url"],
        "LIVE CAMS": res["live_cams"],
        "TOUR CATEGORY ID": res["tour_category_id"],
        "TAGS (separated by commas)": res["tags_en"],
        "TAGS FR": res["tags_fr"],
        "CURATOR NOTES": res["curator_notes"],
    }

    st.subheader("Validation Summary")
    score = int(res.get("accuracy_score_0_100", 0))
    st.write(f"**CW Required:** {'YES' if res['cw_required'] else 'NO'}")
    if res["cw_required"]:
        st.write(f"**CW Label:** {res['cw_label']}")
    st.write(f"**Accuracy Score:** {score}/100")
    st.progress(min(max(score, 0), 100) / 100)

    if score >= 90:
        st.success("Suggested review: Quick skim (10–15 sec)")
    elif 80 <= score < 90:
        st.warning("Suggested review: Light review")
    else:
        st.error("Suggested review: Full human review required")

    with st.expander("Why this score?"):
        reasons = res.get("confidence_reasons", []) or []
        if reasons:
            for r in reasons:
                st.write(f"- {r}")
        else:
            st.write("- No reasons provided.")

    # Download CSV (single row)
    import csv
    import io

    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerow(row)

    st.download_button(
        "⬇️ Download CSV (1 row)",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name="tour_doctor_row.csv",
        mime="text/csv",
    )

    # Download JSON
    st.download_button(
        "⬇️ Download JSON",
        data=json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="tour_doctor_output.json",
        mime="application/json",
    )
