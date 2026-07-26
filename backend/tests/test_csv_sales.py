"""Unit tests for the sales CSV parser (validation rules from api_contracts.md)."""
from app.services.csv_sales import parse_sales_csv

LIMITS = {"max_rows": 100, "max_skus": 10}

VALID = b"""date,sku,product_name,quantity,revenue,price,promo_flag
2026-07-01,MUG-001,Ceramic Mug,10,120.50,12.05,false
2026-07-02,MUG-001,Ceramic Mug,5,60.25,12.05,1
2026-07-01,TSH-022,Logo Tee,3,45.00,15.00,true
"""


def test_valid_csv_parses_all_rows():
    result = parse_sales_csv(VALID, **LIMITS)
    assert len(result.rows) == 3
    assert result.errors == []
    assert result.products == {"MUG-001": "Ceramic Mug", "TSH-022": "Logo Tee"}
    assert result.rows[1]["promo_flag"] is True


def test_bad_date_rejected():
    content = b"date,sku,product_name,quantity,revenue\n07/01/2026,A,Widget,1,10\n"
    result = parse_sales_csv(content, **LIMITS)
    assert result.rows == []
    assert result.errors[0]["field"] == "date"
    assert result.errors[0]["row"] == 2


def test_negative_quantity_rejected():
    content = b"date,sku,product_name,quantity,revenue\n2026-07-01,A,Widget,-1,10\n"
    result = parse_sales_csv(content, **LIMITS)
    assert result.errors[0]["field"] == "quantity"


def test_missing_required_column_fails_fast():
    content = b"date,sku,quantity\n2026-07-01,A,1\n"
    result = parse_sales_csv(content, **LIMITS)
    assert result.rows == []
    assert "product_name" in result.errors[0]["message"]


def test_sku_cap_enforced():
    rows = [b"date,sku,product_name,quantity,revenue"]
    for i in range(12):
        rows.append(f"2026-07-01,SKU-{i},P{i},1,10".encode())
    result = parse_sales_csv(b"\n".join(rows), **LIMITS)
    assert any("SKU limit" in e["message"] for e in result.errors)


def test_bad_promo_flag_rejected():
    content = b"date,sku,product_name,quantity,revenue,promo_flag\n2026-07-01,A,W,1,10,maybe\n"
    result = parse_sales_csv(content, **LIMITS)
    assert result.errors[0]["field"] == "promo_flag"


def test_non_utf8_rejected():
    result = parse_sales_csv(b"\xff\xfe\x00bad", **LIMITS)
    assert result.errors[0]["field"] == "file"
