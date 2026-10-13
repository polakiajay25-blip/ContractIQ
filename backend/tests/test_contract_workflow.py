from backend.app.services.contract_workflow import (
    run_contract_workflow,
)
from backend.app.services.policy_comparator import DEFAULT_POLICY


def test_contract_workflow_extracts_clauses():
    sections = [
        {
            "text": "1. Payment Terms",
            "location": "Page 1",
        },
        {
            "text": "Invoices must be paid within 75 days.",
            "location": "Page 1",
        },
        {
            "text": "2. Liability",
            "location": "Page 1",
        },
        {
            "text": "The parties agree to reasonable liability.",
            "location": "Page 1",
        },
    ]

    result = run_contract_workflow(sections)

    assert result["validation"]["status"] == "completed"
    assert result["validation"]["checks_passed"] is True
    assert len(result["clauses"]) == 2
    assert len(result["findings"]) == 2
    assert len(result["policy_checks"]) == len(DEFAULT_POLICY)


def test_contract_clause_extractor_splits_pdf_page_text_into_headings():
    result = run_contract_workflow(
        [
            {
                "text": (
                    "1. Payment Terms\n"
                    "Invoices must be paid within 75 days.\n"
                    "2. Liability\n"
                    "The parties agree to reasonable liability."
                ),
                "location": "Page 1",
            }
        ]
    )

    assert len(result["clauses"]) == 2
    assert result["clauses"][0]["category"] == "payment_terms"
    assert "75 days" in result["clauses"][0]["clause_text"]
    assert result["clauses"][1]["category"] == "liability"
    assert result["clauses"][1]["source_locations"] == ["Page 1"]


def test_contract_workflow_handles_empty_document():
    result = run_contract_workflow([])

    assert result["validation"]["status"] == "completed"
    assert result["validation"]["checks_passed"] is True
    assert result["clauses"] == []
    assert result["findings"] == []
    assert len(result["policy_checks"]) == len(DEFAULT_POLICY)
