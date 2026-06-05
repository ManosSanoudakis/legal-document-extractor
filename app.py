from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, TypedDict

import streamlit as st

from extractor import GeminiExtractor, run_pipeline
from evaluate import run_evaluation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_PDF = "sample.pdf"

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Party(TypedDict, total=False):
    full_name: str
    tax_id: str
    id_document: str
    address: str

class Representative(TypedDict, total=False):
    full_name: str
    tax_id: str
    id_document: str
    represents: str

class Notary(TypedDict, total=False):
    name: str
    location: str
    registry_number: str

class Property(TypedDict, total=False):
    type: str
    floor: str
    area_sqm: float
    address: str
    municipal_unit: str
    kaek: str
    building_permit: str

class Transaction(TypedDict, total=False):
    deed_type: str
    price: float
    date: str

class ExtractionResult(TypedDict, total=False):
    notary: Notary
    sellers: list[Party]
    buyers: list[Party]
    legal_representatives: list[Representative]
    property: Property
    transaction: Transaction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def display(value: Any) -> str:
    return "" if value is None else str(value)


def resolve_pdf(uploaded_file) -> tuple[str | None, bool]:
    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded_file.read())
            return tmp.name, True
    if Path(DEFAULT_PDF).exists():
        return DEFAULT_PDF, False
    return None, False

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> tuple[str, str]:
    with st.sidebar:
        st.title("⚙️ Settings")
        api_key = st.text_input(
            "Gemini API Key", type="password",
            help="https://aistudio.google.com/apikey",
        )
        model = st.selectbox(
            "Model", GeminiExtractor.MODELS,
            help="flash: fast & cheap  |  pro: more accurate",
        )
    return api_key, model

# ---------------------------------------------------------------------------
# Result renderers
# ---------------------------------------------------------------------------

def render_party(person: Party, prefix: str, index: int) -> None:
    label = person.get("full_name") or "Unknown"
    with st.expander(f"{prefix.capitalize()} {index}: {label}", expanded=True):
        st.text_input(
            "Tax ID", value=display(person.get("tax_id")),
            key=f"{prefix}_tax_{index}", disabled=True,
        )
        st.text_input(
            "ID Document", value=display(person.get("id_document")),
            key=f"{prefix}_id_{index}", disabled=True,
        )
        st.text_input(
            "Address", value=display(person.get("address")),
            key=f"{prefix}_addr_{index}", disabled=True,
        )


def render_results(result: ExtractionResult) -> None:
    notary  = result.get("notary")      or {}
    prop    = result.get("property")    or {}
    txn     = result.get("transaction") or {}
    sellers = result.get("sellers")     or []
    buyers  = result.get("buyers")      or []
    reps = [
        r for r in (result.get("legal_representatives") or [])
        if r.get("full_name")
    ]

    st.divider()
    st.subheader("📊 Extracted Data")

    tab_notary, tab_parties, tab_prop, tab_txn, tab_raw = st.tabs([
        "🏛️ Notary", "👥 Parties", "🏠 Property",
        "💰 Transaction", "📋 Raw JSON",
    ])

    with tab_notary:
        st.markdown("### Notary Details")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Full Name", value=display(notary.get("name")), disabled=True)
        c2.text_input("Location",  value=display(notary.get("location")), disabled=True)
        c3.text_input(
            "Registry Number",
            value=display(notary.get("registry_number")), disabled=True,
        )

    with tab_parties:
        col_s, col_b = st.columns(2)
        with col_s:
            st.markdown("### Sellers")
            if sellers:
                for i, s in enumerate(sellers, 1):
                    render_party(s, "seller", i)
            else:
                st.info("No sellers found.")
        with col_b:
            st.markdown("### Buyers")
            if buyers:
                for i, b in enumerate(buyers, 1):
                    render_party(b, "buyer", i)
            else:
                st.info("No buyers found.")
        if reps:
            st.markdown("### ⚖️ Legal Representatives")
            for i, r in enumerate(reps, 1):
                with st.expander(
                    f"Representative {i}: {r.get('full_name')}", expanded=True
                ):
                    c1, c2 = st.columns(2)
                    c1.text_input(
                        "Represents", value=display(r.get("represents")),
                        key=f"rep_r_{i}", disabled=True,
                    )
                    c2.text_input(
                        "Tax ID", value=display(r.get("tax_id")),
                        key=f"rep_t_{i}", disabled=True,
                    )
                    st.text_input(
                        "ID Document", value=display(r.get("id_document")),
                        key=f"rep_i_{i}", disabled=True,
                    )

    with tab_prop:
        st.markdown("### Property Details")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Type",       value=display(prop.get("type")),     disabled=True)
        c2.text_input("Floor",      value=display(prop.get("floor")),    disabled=True)
        c3.text_input("Area (sqm)", value=display(prop.get("area_sqm")), disabled=True)
        st.text_input("Address", value=display(prop.get("address")), disabled=True)
        st.text_input("Municipal Unit", value=display(prop.get("municipal_unit")),
            disabled=True,
        )
        st.markdown("#### Land Registry")
        c1, c2 = st.columns(2)
        c1.text_input("KAEK", value=display(prop.get("kaek")), disabled=True)
        c2.text_input("Building Permit",
            value=display(prop.get("building_permit")), disabled=True,
        )

    with tab_txn:
        st.markdown("### Transaction Details")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Deed Type", value=display(txn.get("deed_type")), disabled=True)
        c2.text_input("Price",     value=display(txn.get("price")),     disabled=True)
        c3.text_input("Date",      value=display(txn.get("date")),      disabled=True)

    with tab_raw:
        json_str = json.dumps(result, ensure_ascii=False, indent=2)
        st.code(json_str, language="json")
        st.download_button(
            "⬇️ Download JSON", json_str.encode("utf-8"),
            "extracted_legal_data.json", "application/json",
        )


def render_evaluation(report: dict) -> None:
    st.divider()
    st.subheader("📊 Evaluation Results")

    models = report.get("models", [])
    if not models:
        st.warning("No evaluation results available.")
        return

    # Summary metrics table
    col_headers = ["Model", "Overall %", "Scalar %", "List %", "Elapsed (s)", "Status"]
    rows = []
    for m in models:
        c = m.get("completeness") or {}
        rows.append([
            m["model"],
            f"{c.get('overall_pct', 'N/A')}%",
            f"{c.get('scalar_pct',  'N/A')}%",
            f"{c.get('list_pct',    'N/A')}%",
            f"{m.get('elapsed_s', 0):.2f}s",
            "❌ " + m["error"] if m.get("error") else "✅ OK",
        ])

    st.markdown("#### Model Comparison")
    header_cols = st.columns(len(col_headers))
    for col, h in zip(header_cols, col_headers):
        col.markdown(f"**{h}**")
    for row in rows:
        row_cols = st.columns(len(col_headers))
        for col, cell in zip(row_cols, row):
            col.write(cell)

    # Winner banner
    if "winner" in report:
        w = report["winner"]
        st.success(
            f"🏆 **Accuracy** → `{w['accuracy']}`  "
            f"  ⚡ **Speed** → `{w['speed']}`"
        )

    # Field diffs
    diffs = report.get("field_diffs", [])
    if diffs:
        st.markdown("#### Fields Where Models Disagree")
        for d in diffs:
            with st.expander(f"`{d['field']}`", expanded=False):
                c1, c2 = st.columns(2)
                c1.markdown(f"**{models[0]['model']}**")
                c1.write(d["model_a"])
                c2.markdown(f"**{models[1]['model']}**")
                c2.write(d["model_b"])
    else:
        st.info("No disagreements found between models on non-null fields.")

    # Raw JSON download
    json_str = json.dumps(report, ensure_ascii=False, indent=2)
    st.download_button(
        "⬇️ Download Evaluation Report",
        json_str.encode("utf-8"),
        "evaluation_results.json",
        "application/json",
    )

# ---------------------------------------------------------------------------
# Page: Extraction
# ---------------------------------------------------------------------------

def page_extraction(api_key: str, model: str) -> None:
    st.markdown(
        "Extract structured data from Greek notarial deeds "
        "using a Vision Language Model."
    )

    uploaded_file = st.file_uploader("Upload PDF document", type=["pdf"])
    if uploaded_file is None:
        st.info(
            f"💡 No file uploaded — the sample document "
            f"**{DEFAULT_PDF}** will be used."
        )

    if not st.button("🚀 Run Extraction", type="primary", use_container_width=True):
        if "result" in st.session_state:
            render_results(st.session_state["result"])
        return

    if not api_key:
        st.error("❌ Please enter a Gemini API Key in the sidebar.")
        return

    pdf_path, we_own_file = resolve_pdf(uploaded_file)
    if pdf_path is None:
        st.error(f"❌ Sample file not found: **{DEFAULT_PDF}**. Please upload a PDF.")
        return

    try:
        logger.info("Extraction started — model=%s  pdf=%s", model, pdf_path)
        with st.spinner("Processing document…"):
            result: ExtractionResult = run_pipeline(
                pdf_path=pdf_path, api_key=api_key, model_name=model,
            )
        st.success("✅ Extraction complete!")
        st.session_state["result"] = result
    except ConnectionError:
        st.error("❌ Network error — check your API key and internet connection.")
        return
    except ValueError as exc:
        st.error(f"❌ Unexpected response format: {exc}")
        return
    except Exception as exc:
        logger.exception("Unhandled error during extraction")
        st.error(f"❌ Unexpected error: {exc}")
        return
    finally:
        if we_own_file and pdf_path and Path(pdf_path).exists():
            os.unlink(pdf_path)

    render_results(result)

# ---------------------------------------------------------------------------
# Page: Evaluation
# ---------------------------------------------------------------------------

def page_evaluation(api_key: str) -> None:
    st.markdown(
        "Benchmark **Gemini 2.5 Flash** vs **Gemini 2.5 Pro** "
        "on the same document — comparing accuracy and speed."
    )

    uploaded_file = st.file_uploader(
        "Upload PDF document", type=["pdf"], key="eval_upload",
    )
    if uploaded_file is None:
        st.info(
            f"💡 No file uploaded — the sample document "
            f"**{DEFAULT_PDF}** will be used."
        )

    if not st.button(
        "⚡ Run Evaluation", type="primary", use_container_width=True
    ):
        if "eval_report" in st.session_state:
            render_evaluation(st.session_state["eval_report"])
        return

    if not api_key:
        st.error("❌ Please enter a Gemini API Key in the sidebar.")
        return

    pdf_path, we_own_file = resolve_pdf(uploaded_file)
    if pdf_path is None:
        st.error(f"❌ Sample file not found: **{DEFAULT_PDF}**. Please upload a PDF.")
        return

    try:
        with st.spinner(
            "Running Flash + Pro on the same document… this may take ~60s."
        ):
            report = run_evaluation(pdf_path=pdf_path, api_key=api_key)
        st.success("✅ Evaluation complete!")
        st.session_state["eval_report"] = report
    except Exception as exc:
        logger.exception("Unhandled error during evaluation")
        st.error(f"❌ Unexpected error: {exc}")
        return
    finally:
        if we_own_file and pdf_path and Path(pdf_path).exists():
            os.unlink(pdf_path)

    render_evaluation(report)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("⚖️ Legal Document Extractor")
    api_key, model = render_sidebar()

    tab_extract, tab_eval = st.tabs(["📄 Extraction", "📊 Evaluation"])
    with tab_extract:
        page_extraction(api_key, model)
    with tab_eval:
        page_evaluation(api_key)


st.set_page_config(
    page_title="Legal Document Extractor", page_icon="⚖️", layout="wide",
)
main()
