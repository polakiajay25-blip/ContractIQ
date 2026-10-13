def determine_review_status(
    policy_checks: list[dict],
    risk_findings: list[dict],
) -> str:
    """Summarize rule-based findings without implying legal approval."""
    if not policy_checks or any(
        item.get("status") in {
            "needs_review",
            "missing",
            "missing_clause",
        }
        for item in policy_checks
    ):
        return "human_review_required"

    if any(
        item.get("status") == "deviation_detected"
        for item in policy_checks
    ) or any(
        item.get("severity") in {"high", "medium"}
        for item in risk_findings
    ):
        return "attention_required"

    return "no_major_deviation"
