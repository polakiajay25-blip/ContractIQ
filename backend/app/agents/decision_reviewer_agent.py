
def run_decision_reviewer_agent(
    clauses: list[dict],
    risk_findings: list[dict],
    policy_checks: list[dict],
    policy_evidence: list[dict] | None = None,
) -> dict:
    """
    Check whether risk and policy findings have supporting evidence.

    Contract evidence is checked against extracted contract clauses.
    Policy evidence is checked against extracted reference-policy text.

    These are text-presence checks, not legal or semantic validation.
    All findings remain subject to human review.
    """
    issues = []
    policy_evidence = policy_evidence or []

    clause_texts = [
        clause.get("clause_text", "")
        for clause in clauses
        if isinstance(clause.get("clause_text"), str)
    ]

    policy_texts = [
        item.get("text", "")
        for item in policy_evidence
        if isinstance(item.get("text"), str)
    ]

    def evidence_check(
        evidence: object,
        source_texts: list[str],
    ) -> tuple[bool, bool]:
        if not isinstance(evidence, str) or not evidence.strip():
            return False, False

        evidence = evidence.strip()
        found = any(
            evidence.casefold() in source.casefold()
            for source in source_texts
        )
        return True, found

    for finding in risk_findings:
        evidence = finding.get("evidence")
        present, found = evidence_check(evidence, clause_texts)

        issues.append({
            "item_type": "risk_finding",
            "item": finding.get("risk_type", "unknown"),
            "evidence_present": present,
            "evidence_found_in_contract": found,
            "review_required": True,
            "review_status": "pending",
            "verification_note": (
                "Evidence text found in extracted contract."
                if found
                else "Contract evidence is missing or was not matched."
            ),
        })

    for check in policy_checks:
        contract_evidence = check.get("evidence")
        contract_present, contract_found = evidence_check(
            contract_evidence, clause_texts
        )

        policy_quote = check.get("policy_evidence")
        policy_present, policy_found = evidence_check(
            policy_quote, policy_texts
        )

        # A policy quote is not considered verified just because it
        # was selected by the comparator's keyword-based heuristic.
        policy_verification = (
            "not_checked"
            if not policy_present
            else "text_match"
            if policy_found
            else "text_not_matched"
        )

        issues.append({
            "item_type": "policy_check",
            "item": check.get("category", "unknown"),
            "comparison_status": check.get("status", "unknown"),
            "contract_evidence_present": contract_present,
            "contract_evidence_found": contract_found,
            "policy_evidence_present": policy_present,
            "policy_evidence_found": policy_found,
            "policy_evidence_verification": policy_verification,
            "review_required": True,
            "review_status": "pending",
        })

    return {
        "status": "review_required" if issues else "checks_completed",
        "clause_count": len(clauses),
        "risk_finding_count": len(risk_findings),
        "policy_check_count": len(policy_checks),
        "items": issues,
        "human_review_required": bool(issues),
        "notice": (
            "Evidence checks verify text presence only. They do not "
            "confirm semantic accuracy, policy compliance, or legal "
            "correctness. Human review is required."
        ),
    }
