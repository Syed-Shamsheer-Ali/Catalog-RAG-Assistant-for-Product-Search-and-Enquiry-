from app.views.product_grid import build_grid_rows, merge_grid_rows


def test_grid_maps_catalog_package_price_and_row_editing():
    source = [{
        "line_item_id": "line-1", "product_name": "90 degree elbow", "size_inch": "1/2",
        "specifications": "CPVC", "quantity": "300", "number_of_boxes": 3,
    }]
    prepared = [{
        **source[0], "part_number": "70000537", "quantity_per_box": 100,
        "number_of_boxes": 3, "total_quantity": 300, "unit_price": 26.0,
        "price_source": "local_catalog", "price_basis": "piece", "line_total": 7800.0,
        "catalog_match_status": "Matched", "price_match_details": {"price_type": "PER_PIECE"},
    }]
    rows = build_grid_rows(source, prepared)

    assert rows[0]["Quantity per Box"] == 100
    assert rows[0]["Number of Boxes"] == 3
    assert rows[0]["Total Quantity"] == 300
    assert rows[0]["Unit Price"].endswith("/ piece")
    assert rows[0]["Total Price"].endswith("7,800.00")
    rows[0]["Number of Boxes"] = 4
    rows[0]["Actions"] = False
    updated, removed = merge_grid_rows(rows, source, prepared)
    assert not removed
    assert updated[0]["number_of_boxes"] == 4
    assert updated[0]["quantity"] == 300


def test_grid_marks_unmatched_rows_and_remove_action():
    source = [{"line_item_id": "line-unknown", "product_name": "Unlisted coupling", "quantity": "2"}]
    prepared = [{**source[0], "catalog_match_status": "Not Found", "validation_errors": ["No catalog price"]}]
    row = build_grid_rows(source, prepared)[0]
    assert row["Status"] == "Needs Review"
    assert row["Unit Price"] == "Needs Review"
    row["Actions"] = True
    updated, removed = merge_grid_rows([row], source, prepared)
    assert updated == []
    assert removed == ["line-unknown"]
