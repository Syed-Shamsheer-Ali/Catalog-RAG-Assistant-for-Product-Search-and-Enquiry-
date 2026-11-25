from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.controllers.requirement_controller import RequirementController
from app.controllers.submission_controller import SubmissionController
from app.invoice import render_invoice_html
from app.services.catalog_chat_service import answer_catalog_question
from app.views.product_grid import GRID_COLUMNS, RUPEE, build_grid_rows, merge_grid_rows


def _candidate_label(candidate: dict) -> str:
    name = str(candidate.get("product_name") or candidate.get("product_id") or "Unnamed product")
    size = str(candidate.get("size_inch") or candidate.get("compound_size") or "")
    part_number = str(candidate.get("part_number") or "No part number")
    price = candidate.get("price")
    try:
        price_text = f"{RUPEE}{float(price):,.2f}" if price not in (None, "") else "Price unavailable"
    except (TypeError, ValueError):
        price_text = "Price unavailable"
    details = [name]
    if size:
        details.append(size)
    details.append(f"Part: {part_number}")
    details.append(price_text)
    return " · ".join(details)


def _render_catalog_chat() -> None:
    st.markdown(
        """
        <style>
        .st-key-catalog-chat-launcher {
            position: fixed !important;
            right: 40px !important;
            bottom: 40px !important;
            width: 76px !important;
            z-index: 100000 !important;
        }
        .st-key-catalog-chat-launcher [data-testid="stButton"] button {
            width: 68px;
            height: 68px;
            border-radius: 50%;
            padding: 0;
            font-size: 32px;
            color: #fff;
            background: #2457d6;
            border: 2px solid #fff;
            box-shadow: 0 5px 20px rgba(0, 0, 0, .38);
            transition: transform .15s ease, background-color .15s ease;
        }
        .st-key-catalog-chat-launcher [data-testid="stButton"] button:hover {
            background: #1743b5;
            transform: scale(1.06);
        }
        .st-key-catalog-chat-panel {
            position: fixed !important;
            right: 22px !important;
            bottom: 124px !important;
            top: 100px !important;
            width: 410px !important;
            max-width: calc(100vw - 32px) !important;
            height: auto !important;
            max-height: none !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
            padding: 14px 16px 104px;
            border: 1px solid rgba(128, 128, 128, .35);
            border-radius: 16px;
            background: var(--background-color);
            box-shadow: 0 8px 32px rgba(0, 0, 0, .32);
            z-index: 99999 !important;
        }
        .st-key-catalog-chat-footer {
            position: fixed !important;
            right: 38px !important;
            bottom: 132px !important;
            width: 378px !important;
            max-width: calc(100vw - 48px) !important;
            z-index: 100001 !important;
            padding: 8px 10px 4px;
            background: var(--background-color);
            border-top: 1px solid rgba(128, 128, 128, .25);
            border-radius: 10px;
            box-sizing: border-box;
        }
        .st-key-catalog-chat-footer [data-testid="stForm"] {
            width: 100% !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
        }
        .st-key-catalog-chat-footer [data-testid="stHorizontalBlock"] {
            gap: 8px !important;
        }
        .st-key-catalog-chat-footer [data-testid="stTextInput"] {
            min-width: 0 !important;
        }
        .st-key-catalog-chat-footer [data-testid="stFormSubmitButton"] button {
            min-width: 64px !important;
            white-space: nowrap !important;
        }
        .st-key-catalog-chat-messages {
            max-height: calc(100vh - 360px) !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            min-height: 0 !important;
            padding-right: 8px;
            scrollbar-width: thin;
        }
        @media (max-width: 600px) {
            .st-key-catalog-chat-launcher { right: 24px !important; bottom: 24px !important; }
            .st-key-catalog-chat-launcher [data-testid="stButton"] button {
                width: 64px;
                height: 64px;
                font-size: 30px;
            }
            .st-key-catalog-chat-panel {
                right: 8px !important;
                bottom: 100px !important;
                width: calc(100vw - 16px) !important;
                top: 88px !important;
                max-width: calc(100vw - 16px) !important;
            }
            .st-key-catalog-chat-footer {
                right: 24px !important;
                bottom: 108px !important;
                width: calc(100vw - 48px) !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if "catalog_chat_open" not in st.session_state:
        st.session_state.catalog_chat_open = False
    if "catalog_chat_messages" not in st.session_state:
        st.session_state.catalog_chat_messages = [{
            "role": "assistant",
            "content": "Hi! I can answer product enquiries and look up catalog details for pipe, fitting, valve, accessory, and cement products. If form autofill misses an item, ask by product, size, specification, or part number.",
            "matches": [],
        }]
    pending_prompt = st.session_state.pop("catalog_chat_pending_prompt", None)
    if pending_prompt:
        # Set the widget value before it is instantiated during this rerun.
        st.session_state["catalog_chat_prompt"] = pending_prompt

    if st.session_state.catalog_chat_open:
        st.markdown(
            """
            <style>
            @media (min-width: 800px) {
                section[data-testid="stMain"], .main {
                    padding-right: 460px !important;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    with st.container(key="catalog-chat-launcher"):
        if st.button("💬", key="open_catalog_chat", help="Chat with the catalog assistant"):
            st.session_state.catalog_chat_open = not st.session_state.catalog_chat_open
            st.rerun()

    if not st.session_state.catalog_chat_open:
        return

    with st.container(key="catalog-chat-panel"):
        title_col, close_col = st.columns([5, 1], vertical_alignment="center")
        title_col.markdown("### Catalog assistant")
        if close_col.button("✕", key="close_catalog_chat", help="Close chat"):
            st.session_state.catalog_chat_open = False
            st.rerun()

        with st.container(key="catalog-chat-messages"):
            for message in st.session_state.catalog_chat_messages:
                with st.chat_message(message.get("role", "assistant")):
                    st.write(message.get("content", ""))
                    matches = message.get("matches") or []
                    if matches:
                        with st.expander(f"Catalog references ({len(matches)})"):
                            for match in matches:
                                st.markdown(f"**{match.get('product_name') or 'Catalog product'}**")
                                detail_values = [
                                    f"Part: {match.get('part_number') or 'not listed'}",
                                    f"Size: {match.get('size_inch') or match.get('compound_size') or 'not listed'}",
                                ]
                                if match.get("price") is not None:
                                    try:
                                        price_text = f"{RUPEE}{float(match['price']):,.2f}"
                                    except (TypeError, ValueError):
                                        price_text = "unavailable"
                                    detail_values.append(f"Price: {price_text} / {match.get('price_type') or 'catalog basis'}")
                                st.caption(" · ".join(detail_values))
                                source = match.get("source_document") or "Local catalog"
                                page = match.get("source_page")
                                st.caption(f"Source: {source}" + (f", page {page}" if page else ""))

    with st.container(key="catalog-chat-footer"):
        with st.form("catalog_chat_form", clear_on_submit=True):
            prompt_col, send_col = st.columns([5, 1], vertical_alignment="bottom")
            prompt = prompt_col.text_input(
                "Message catalog assistant",
                placeholder="Ask about a product or part number…",
                label_visibility="collapsed",
                key="catalog_chat_prompt",
            )
            submitted = send_col.form_submit_button("Send", use_container_width=True)

    if submitted and prompt.strip():
        previous_messages = list(st.session_state.catalog_chat_messages)
        st.session_state.catalog_chat_messages.append({"role": "user", "content": prompt.strip()})
        with st.spinner("Searching the product catalog…"):
            result = answer_catalog_question(prompt.strip(), previous_messages)
        st.session_state.catalog_chat_messages.append({
            "role": "assistant",
            "content": result["answer"],
            "matches": result.get("matches", []),
        })
        st.rerun()


def _append_items(controller: RequirementController, items: list[dict]) -> None:
    if not items:
        st.warning("No product lines were extracted. Add or edit product details manually.")
        return
    current = list(st.session_state.get("line_items", []))
    for item in items:
        value = dict(item)
        value.setdefault("line_item_id", str(uuid4()))
        value.setdefault("product_name", "")
        value.setdefault("specifications", ", ".join(str(value.get(key)) for key in ("material", "system") if value.get(key)))
        value.setdefault("duplicate_confirmed", False)
        current.append(value)
    st.session_state.line_items = current
    st.session_state.grid_generation = int(st.session_state.get("grid_generation", 0)) + 1


def _render_input_tabs(controller: RequirementController) -> None:
    text_tab, image_tab, voice_tab, sheet_tab = st.tabs(["Type or paste", "Upload bill (image/PDF)", "Record voice", "Import spreadsheet"])
    with text_tab:
        text = st.text_area("Paste a list or bill items (one item per line)", height=110, key="multi_text", placeholder="110mm pipe, quantity 50\n110mm plain bend, quantity 64")
        if st.button("Add items", key="extract_text"):
            _append_items(controller, controller.extract_many(text=text))
    with image_tab:
        images = st.file_uploader("Choose bill images or text PDFs", type=["png", "jpg", "jpeg", "bmp", "webp", "pdf"], accept_multiple_files=True, key="multi_images")
        if st.button("Read images and add items", key="extract_images"):
            paths: list[str] = []
            try:
                for image in images or []:
                    suffix = Path(image.name).suffix or ".img"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                        handle.write(image.getvalue())
                        paths.append(handle.name)
                _append_items(controller, controller.extract_many(image_paths=paths))
            except Exception as error:
                st.error(f"Image extraction failed: {error}")
            finally:
                for path in paths:
                    Path(path).unlink(missing_ok=True)
    with voice_tab:
        audio = st.audio_input("Record the requested products", key="multi_audio")
        language = st.selectbox("Language", ["Auto detect", "English", "Hindi", "Telugu"], key="multi_voice_language")
        language_code = {"Auto detect": None, "English": "en", "Hindi": "hi", "Telugu": "te"}[language]
        if st.button("Transcribe and add items", key="extract_voice"):
            if audio is None:
                st.warning("Record audio before extracting products.")
            else:
                _append_items(controller, controller.extract_many(audio=audio, language=language_code))
    with sheet_tab:
        sheets = st.file_uploader("Choose a bill or item list (.csv, .xlsx)", type=["csv", "xlsx", "xlsm"], accept_multiple_files=True, key="multi_sheet")
        if st.button("Import rows as items", key="extract_sheet"):
            if not sheets:
                st.warning("Choose a CSV or Excel file first.")
            else:
                try:
                    imported = []
                    for sheet in sheets:
                        imported.extend(controller.service.extract_spreadsheet(sheet.getvalue(), sheet.name))
                    _append_items(controller, imported)
                except Exception as error:
                    st.error(f"Spreadsheet import failed: {error}")


def render_ui() -> None:
    st.title("Create a pipe supply estimate")
    st.caption("Add requested items, review local catalog pricing, and create the estimate.")
    controller = RequirementController()
    if "line_items" not in st.session_state:
        st.session_state.line_items = []
    if "grid_generation" not in st.session_state:
        st.session_state.grid_generation = 0
    _render_catalog_chat()

    st.subheader("1. Customer")
    customer_name = st.text_input("Customer or company name", key="multi_customer_name", placeholder="Enter customer name")

    st.subheader("2. Add items")
    with st.expander("Import from text, image/PDF, voice, or spreadsheet", expanded=not st.session_state.line_items):
        _render_input_tabs(controller)
    if st.button("Add Item", key="add_product_row"):
        _append_items(controller, [{"product_name": "", "product_kind": "", "product_category": "", "size_inch": "", "specifications": "", "material": "", "system": "", "quantity": "", "unit": "", "part_number": "", "notes": "", "duplicate_confirmed": False}])

    st.subheader("3. Product Requirements")
    if not st.session_state.line_items:
        st.info("Import a document or choose **Add Item** to start a product row.")
        return

    source_items = [dict(item) for item in st.session_state.line_items]
    initial_prepared = controller.prepare_line_items(source_items)["line_items"]
    rows = build_grid_rows(source_items, initial_prepared)
    st.caption("Enter Number of Boxes to use the catalog pack size. Leave it blank to enter loose pieces, meters, or fixed pipe lengths in Total Quantity.")
    grid_generation = int(st.session_state.grid_generation)
    edited_rows: list[dict] = []
    for row_index, row in enumerate(rows):
        line_id = str(row.get("line_item_id") or uuid4())
        row_key = f"requirement_{grid_generation}_{line_id}"
        values = dict(row)
        prepared_row = initial_prepared[row_index] if row_index < len(initial_prepared) else {}
        source_row = source_items[row_index]

        with st.container(border=True):
            title_col, status_col, remove_col = st.columns([6, 2, 1], vertical_alignment="center")
            item_title = str(row.get("Item Name") or "Unnamed product").strip()
            title_col.markdown(f"**Item {row_index + 1}: {item_title}**")
            status = str(row.get("Status") or "Needs Review")
            if status == "Matched":
                status_col.success(status, icon="✅")
            else:
                status_col.warning(status, icon="⚠️")
                inquiry_parts = [
                    str(values.get("Item Name") or "").strip(),
                    str(values.get("Size / Specification") or "").strip(),
                ]
                part_number = str(values.get("Product Code / Part Number") or "").strip()
                inquiry_details = [value for value in inquiry_parts if value]
                if part_number:
                    inquiry_details.append(f"part number {part_number}")
                inquiry = " | ".join(inquiry_details) or f"item {row_index + 1}"
                if st.button(
                    "Ask assistant for details",
                    key=f"{row_key}_ask_catalog",
                    help="Open a read-only catalog enquiry with this item's details prefilled.",
                ):
                    st.session_state.catalog_chat_pending_prompt = (
                        f"Find catalog details for {inquiry}. Show the closest relevant catalog records."
                    )
                    st.session_state.catalog_chat_open = True
                    st.rerun()
            if remove_col.button("Remove", key=f"{row_key}_remove", help="Remove this product row"):
                st.session_state.line_items = [
                    item for item_index, item in enumerate(source_items)
                    if str(item.get("line_item_id") or "") != line_id
                    and not (not item.get("line_item_id") and item_index == row_index)
                ]
                st.session_state.grid_generation += 1
                st.rerun()

            field_layout = [
                (("Item Name", "name"), ("Size / Specification", "spec"), ("Product Code / Part Number", "part")),
                (("Quantity per Box", "pack"), ("Number of Boxes", "boxes"), ("Total Quantity", "quantity"), ("Unit", "unit")),
            ]
            for field_row in field_layout:
                cells = st.columns([3, 2, 2] if len(field_row) == 3 else [1, 1, 1, 1])
                for cell, (field, key_suffix) in zip(cells, field_row):
                    widget_key = f"{row_key}_{key_suffix}"
                    initial_value = values.get(field)
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = "" if initial_value is None else str(initial_value)
                    cell.text_input(
                        field, key=widget_key,
                        placeholder="Enter product name" if field == "Item Name" else "Enter quantity" if field == "Total Quantity" else "—",
                        help=("Catalog pack capacity; editable when missing." if field == "Quantity per Box" else
                              "Enter piece, box, m, or length. The catalog price basis is checked on review." if field == "Unit" else None),
                    )
                    values[field] = st.session_state[widget_key]

            candidates = list(prepared_row.get("matches") or [])
            current_selected_id = str(source_row.get("selected_product_id") or "")
            needs_choice = bool(candidates) and (
                prepared_row.get("match_ambiguous")
                or prepared_row.get("catalog_match_status") != "Matched"
                or bool(current_selected_id)
            )
            if needs_choice:
                st.caption("Choose the catalog item that best matches this requirement. Search by product name or part number.")
                candidate_by_id = {
                    str(candidate.get("product_id") or ""): candidate
                    for candidate in candidates
                    if candidate.get("product_id")
                }
                candidate_ids = list(candidate_by_id)
                options = [""] + candidate_ids
                selected_index = options.index(current_selected_id) if current_selected_id in options else 0
                selected_candidate = st.selectbox(
                    "Matching catalog products",
                    options,
                    index=selected_index,
                    format_func=lambda product_id: "Search or select a product…" if not product_id else _candidate_label(candidate_by_id[product_id]),
                    key=f"{row_key}_candidate",
                    label_visibility="collapsed",
                )
                if selected_candidate != current_selected_id:
                    if selected_candidate:
                        source_row["selected_product_id"] = selected_candidate
                    else:
                        source_row.pop("selected_product_id", None)
                    st.session_state.line_items = source_items
                    st.rerun()

            price_col, total_col, basis_col = st.columns([1, 1, 2])
            price_col.metric("Unit price", str(row.get("Unit Price") or "Needs Review"))
            total_col.metric("Line total", str(row.get("Total Price") or "—"))
            price_basis = str(prepared_row.get("price_basis") or "")
            if price_basis:
                basis_col.caption(f"Catalog price basis: {price_basis}")

        values["line_item_id"] = line_id
        edited_rows.append(values)

    edited_items, removed_ids = merge_grid_rows(edited_rows, source_items, initial_prepared)
    if removed_ids:
        st.session_state.line_items = [item for item in edited_items if item.get("line_item_id") not in removed_ids]
        st.session_state.grid_generation += 1
        st.rerun()

    editable_columns = ["Item Name", "Size / Specification", "Product Code / Part Number", "Quantity per Box", "Number of Boxes", "Total Quantity", "Unit"]
    changed = any(
        any(str(row.get(column) or "") != str(base.get(column) or "") for column in editable_columns)
        for row, base in zip(edited_rows, rows)
    )
    if changed:
        st.session_state.line_items = edited_items
        st.session_state.grid_generation += 1
        st.rerun()

    st.session_state.line_items = edited_items
    prepared = controller.prepare_line_items(edited_items)
    warnings = [
        f"Row {index}: {item['validation_errors'][0]}"
        for index, item in enumerate(prepared["line_items"], start=1)
        if item.get("validation_errors")
    ]
    for warning in warnings:
        st.caption(f"⚠ {warning}")

    total_col, basis_col = st.columns([1, 3])
    with total_col:
        total_text = f"{RUPEE}{prepared['grand_total']:,.2f}" if prepared["grand_total"] is not None else "Pending review"
        st.metric("Grand Total", total_text)
    with basis_col:
        st.caption("Unit prices show their catalog basis: piece, box, meter, or fixed pipe length. Unmatched products stay editable and unpriced.")

    confirmed = st.checkbox("I have reviewed the items, quantities, units, and local catalog prices", key="confirm_all_lines")
    if st.button("Create estimate", type="primary", key="submit_all_lines"):
        result = SubmissionController().submit({"customer_name": customer_name, "line_items": edited_items}, confirmed=confirmed)
        if not result.get("success"):
            for error in result.get("validation_errors", []):
                st.error(error)
            if not result.get("validation_errors"):
                st.warning(result.get("message", "Requirements were not finalized."))
        else:
            report = result["report"]
            st.success(result["message"])
            st.markdown(render_invoice_html(report))
            st.metric("Estimate total", f"{RUPEE}{result['grand_total']:,.2f}")
            for file_type, label, mime in (("pdf_path", "Download PDF", "application/pdf"), ("csv_path", "Download CSV", "text/csv"), ("json_path", "Download JSON", "application/json")):
                path = result.get("export", {}).get(file_type)
                if path:
                    with open(path, "rb") as handle:
                        st.download_button(label, handle.read(), file_name=Path(path).name, mime=mime, key=f"download_{file_type}")

if __name__ == "__main__":
    render_ui()
