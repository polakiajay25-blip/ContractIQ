
from backend.app.services.policy_comparator import compare_with_policy


def get_payment_result(results):
    return next(
        result
        for result in results
        if result["category"] == "payment_terms"
    )


def test_payment_period_exceeds_policy():
    clauses = [
        {
            "heading": "2. Payment Terms",
            "category": "payment_terms",
            "clause_text": (
                "The Client shall pay all invoices within 90 days."
            ),
            "source_locations": ["Paragraph 6"],
        }
    ]

    results = compare_with_policy(clauses)
    payment_result = get_payment_result(results)

    assert payment_result["status"] == "deviation_detected"
    assert "90 days" in payment_result["evidence"]


def test_payment_period_within_policy():
    clauses = [
        {
            "heading": "2. Payment Terms",
            "category": "payment_terms",
            "clause_text": (
                "The Client shall pay all invoices within 15 days."
            ),
            "source_locations": ["Paragraph 6"],
        }
    ]

    results = compare_with_policy(clauses)
    payment_result = get_payment_result(results)

    assert payment_result["status"] == "no_deviation_detected"


def test_missing_payment_clause():
    results = compare_with_policy([])

    payment_result = get_payment_result(results)

    assert payment_result["status"] == "missing_clause"


def test_policy_result_has_source_and_review_status():
    clauses = [
        {
            "heading": "2. Payment Terms",
            "category": "payment_terms",
            "clause_text": (
                "The Client shall pay all invoices within 90 days."
            ),
            "source_locations": ["Paragraph 6"],
        }
    ]

    results = compare_with_policy(clauses)
    payment_result = get_payment_result(results)

    assert payment_result["source_locations"] == ["Paragraph 6"]
    assert payment_result["review_status"] == "pending"

def test_policy_result_includes_contract_requirement_and_difference():
    clauses = [
        {
            "heading": "2. Payment Terms",
            "category": "payment_terms",
            "clause_text": (
                "The Client shall pay all invoices within 90 days."
            ),
            "source_locations": ["Paragraph 6"],
        }
    ]

    results = compare_with_policy(clauses)
    payment_result = get_payment_result(results)

    assert payment_result["policy_requirement"]
    assert payment_result["evidence"]
    assert payment_result["source_locations"] == ["Paragraph 6"]
    assert payment_result["review_status"] == "pending"
    assert payment_result["status"] == "deviation_detected"
    assert "90 days" in payment_result["explanation"]
    assert "30 days" in payment_result["explanation"]

def test_service_availability_below_policy_target():
    clauses = [{
        "category": "service_availability",
        "clause_text": "The service guarantees 99.5% uptime.",
        "source_locations": ["Paragraph 10"],
    }]
    policy = {
        "service_availability": {
            "require_uptime_target": True,
            "minimum_uptime_percent": 99.9,
            "description": "Service uptime must be at least 99.9%.",
        }
    }

    results = compare_with_policy(clauses, policy=policy)
    result = next(r for r in results
                  if r["category"] == "service_availability")

    assert result["status"] == "deviation_detected"


def test_service_availability_meets_policy_target():
    clauses = [{
        "category": "service_availability",
        "clause_text": "The service guarantees 99.95% uptime.",
        "source_locations": ["Paragraph 10"],
    }]
    policy = {
        "service_availability": {
            "require_uptime_target": True,
            "minimum_uptime_percent": 99.9,
            "description": "Service uptime must be at least 99.9%.",
        }
    }

    results = compare_with_policy(clauses, policy=policy)
    result = next(r for r in results
                  if r["category"] == "service_availability")

    assert result["status"] == "no_deviation_detected"


def test_security_notification_exceeds_policy_deadline():
    clauses = [{
        "category": "security_incident",
        "clause_text": "Security incidents must be reported within 96 hours.",
        "source_locations": ["Paragraph 12"],
    }]
    policy = {
        "security_incident": {
            "require_notification_deadline": True,
            "max_notification_hours": 72,
            "description": "Incidents must be reported within 72 hours.",
        }
    }

    results = compare_with_policy(clauses, policy=policy)
    result = next(r for r in results
                  if r["category"] == "security_incident")

    assert result["status"] == "deviation_detected"


def test_security_notification_meets_policy_deadline():
    clauses = [{
        "category": "security_incident",
        "clause_text": "Security incidents must be reported within 48 hours.",
        "source_locations": ["Paragraph 12"],
    }]
    policy = {
        "security_incident": {
            "require_notification_deadline": True,
            "max_notification_hours": 72,
            "description": "Incidents must be reported within 72 hours.",
        }
    }

    results = compare_with_policy(clauses, policy=policy)
    result = next(r for r in results
                  if r["category"] == "security_incident")

    assert result["status"] == "no_deviation_detected"

from backend.app.services.policy_rule_extractor import (
    extract_policy_rules,
)


def test_uploaded_policy_numeric_deviations():
    policy_text = (
        "Invoices must be paid within 30 days. "
        "Minimum service availability is 99.9%. "
        "Security incidents must be reported within 72 hours."
    )

    # Extract rules from the policy text, as the application does.
    policy_result = extract_policy_rules(policy_text)
    policy = policy_result["rules"]

    clauses = [
        {
            "category": "payment_terms",
            "heading": "Payment Terms",
            "clause_text": (
                "The Client shall pay all invoices within 45 days."
            ),
            "source_locations": ["Paragraph 6"],
        },
        {
            "category": "service_availability",
            "heading": "Service Availability",
            "clause_text": (
                "The service guarantees 99.5% availability."
            ),
            "source_locations": ["Paragraph 10"],
        },
        {
            "category": "security_incident",
            "heading": "Security Incident Notification",
            "clause_text": (
                "Security incidents must be reported within 96 hours."
            ),
            "source_locations": ["Paragraph 12"],
        },
    ]

    # Compare using the extracted rules, not DEFAULT_POLICY.
    results = compare_with_policy(clauses, policy=policy)

    results_by_category = {
        result["category"]: result for result in results
    }

    assert (
        policy["payment_terms"]["max_payment_days"] == 30
    )
    assert (
        policy["service_availability"]["minimum_uptime_percent"]
        == 99.9
    )
    assert (
        policy["security_incident"]["max_notification_hours"]
        == 72
    )

    assert (
        results_by_category["payment_terms"]["status"]
        == "deviation_detected"
    )
    assert (
        results_by_category["service_availability"]["status"]
        == "deviation_detected"
    )
    assert (
        results_by_category["security_incident"]["status"]
        == "deviation_detected"
    )
