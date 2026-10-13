
import re


def analyze_clause_risks(clauses: list[dict]) -> list[dict]:
    """
    Identify potential contract issues using transparent rules.

    These findings are review flags, not definitive legal conclusions.
    """
    findings = []

    def add_finding(
        clause: dict,
        risk_type: str,
        severity: str,
        description: str,
        evidence: str,
        recommendation: str,
    ):
        findings.append({
            "clause_heading": clause.get("heading", "Unknown"),
            "category": clause.get("category", "other"),
            "risk_type": risk_type,
            "severity": severity,
            "description": description,
            "evidence": evidence,
            "source_locations": clause.get("source_locations", []),
            "recommendation": recommendation,
            "review_status": "pending",
        })

    for clause in clauses:
        category = clause.get("category", "other")
        text = clause.get("clause_text", "").strip()
        normalized = text.lower()

        if not text:
            continue

        # Payment terms: flag unusually long payment periods.
        if category == "payment_terms":
            days_match = re.search(
                r"\b(\d{1,3})\s+days?\b",
                normalized,
            )

            if days_match:
                days = int(days_match.group(1))

                if days > 60:
                    add_finding(
                        clause,
                        "long_payment_period",
                        "medium",
                        f"The payment period is {days} days, "
                        "which may create cash-flow concerns.",
                        days_match.group(0),
                        "Compare the payment period with the "
                        "organization's approved payment policy.",
                    )

        # Liability: look for an explicit monetary or formula-based cap.
        elif category == "liability":
            has_cap = bool(
                re.search(
                    r"\b(cap|capped|shall not exceed|"
                    r"maximum aggregate liability|limited to)\b",
                    normalized,
                )
            )

            if not has_cap:
                add_finding(
                    clause,
                    "liability_cap_unclear",
                    "high",
                    "An explicit liability cap was not detected "
                    "by the current rule.",
                    text,
                    "Ask an authorized reviewer to confirm whether "
                    "the liability limit is clearly defined.",
                )

        # Intellectual property: flag ownership deferred elsewhere.
        elif category == "intellectual_property":
            deferred_terms = [
                "separate written agreement",
                "to be agreed",
                "will be determined separately",
                "subject to a separate agreement",
            ]

            matched_term = next(
                (
                    term for term in deferred_terms
                    if term in normalized
                ),
                None,
            )

            if matched_term:
                add_finding(
                    clause,
                    "ip_ownership_deferred",
                    "high",
                    "Intellectual-property ownership appears "
                    "to depend on a separate agreement.",
                    text,
                    "Confirm that the relevant agreement defines "
                    "ownership, permitted use, and applicable rights.",
                )

        # Confidentiality: check for an explicit duration.
        elif category == "confidentiality":
            duration_terms = [
                "years after termination",
                "months after termination",
                "survive termination",
                "perpetual",
                "indefinitely",
            ]

            if not any(
                term in normalized for term in duration_terms
            ):
                add_finding(
                    clause,
                    "confidentiality_duration_unclear",
                    "medium",
                    "An explicit confidentiality duration was "
                    "not detected by the current rule.",
                    text,
                    "Review whether the confidentiality period "
                    "and any exceptions should be specified.",
                )

        # Dispute resolution: check for a formal procedure.
        elif category == "dispute_resolution":
            formal_terms = [
                "arbitration",
                "court",
                "jurisdiction",
                "mediation",
                "venue",
            ]

            if not any(
                term in normalized for term in formal_terms
            ):
                add_finding(
                    clause,
                    "formal_dispute_process_unclear",
                    "medium",
                    "The clause does not explicitly mention a "
                    "formal dispute-resolution mechanism.",
                    text,
                    "Ask a qualified reviewer whether the process, "
                    "venue, or applicable procedure needs clarification.",
                )

    return findings
