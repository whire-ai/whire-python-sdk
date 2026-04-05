"""Tests for mandate building and hash verification."""

import hashlib
import json
from decimal import Decimal

from whire.mandate import build_payment_mandate


def test_build_payment_mandate_structure():
    """Mandate has required top-level keys."""
    mandate = build_payment_mandate(
        mandate_id="test-001",
        payment_details_id="pd-001",
        amount=Decimal("50.00"),
        label="Test",
        account_id="acc-123",
        recipient_id="rcp-001",
        merchant_agent="test-agent",
    )

    assert "payment_mandate_contents" in mandate
    assert "user_authorization" in mandate
    assert isinstance(mandate["user_authorization"], str)
    assert len(mandate["user_authorization"]) == 64  # SHA-256 hex


def test_build_payment_mandate_hash_matches():
    """Hash matches recomputed SHA-256 of contents."""
    mandate = build_payment_mandate(
        mandate_id="test-002",
        payment_details_id="pd-002",
        amount=Decimal("25.00"),
        label="Test Payment",
        account_id="acc-456",
        recipient_id="rcp-001",
        merchant_agent="test-agent",
    )

    contents = mandate["payment_mandate_contents"]
    payload = json.dumps(contents, separators=(",", ":"), sort_keys=False)
    expected_hash = hashlib.sha256(payload.encode()).hexdigest()

    assert mandate["user_authorization"] == expected_hash


def test_build_payment_mandate_details_correct():
    """Transfer details are correctly nested."""
    mandate = build_payment_mandate(
        mandate_id="test-005",
        payment_details_id="pd-005",
        amount=Decimal("75.50"),
        label="Invoice 42",
        account_id="acc-xyz",
        recipient_id="rcp-005",
        merchant_agent="my-agent",
    )

    contents = mandate["payment_mandate_contents"]
    assert contents["payment_mandate_id"] == "test-005"
    assert contents["payment_details_total"]["amount"] == "75.50"
    assert contents["payment_details_total"]["currency"] == "EUR"

    details = contents["payment_response"]["details"]
    assert details["account_id"] == "acc-xyz"
    assert details["recipient_id"] == "rcp-005"


def test_different_mandates_different_hashes():
    """Two mandates with different data produce different hashes."""
    m1 = build_payment_mandate(
        mandate_id="a",
        payment_details_id="pd-a",
        amount=Decimal("10.00"),
        label="A",
        account_id="acc",
        recipient_id="rcp-a",
        merchant_agent="agent",
    )
    m2 = build_payment_mandate(
        mandate_id="b",
        payment_details_id="pd-b",
        amount=Decimal("20.00"),
        label="B",
        account_id="acc",
        recipient_id="rcp-b",
        merchant_agent="agent",
    )

    assert m1["user_authorization"] != m2["user_authorization"]
