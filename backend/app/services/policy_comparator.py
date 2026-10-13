
import re


# Example reference policy for development and testing.
DEFAULT_POLICY = {
    "payment_terms": {
        "max_payment_days": 30,
        "description": "Invoices should be paid within 30 days.",
    },
    "confidentiality": {
        "require_duration": True,
        "description": (
            "The confidentiality duration should be specified."
        ),
    },
    "liability": {
        "require_explicit_cap": True,
        "description": (
            "Liability limits should be clearly documented."
        ),
    },
    "intellectual_property": {
        "require_explicit_ownership": True,
        "description": (
            "Intellectual-property ownership should be documented."
        ),
    },
    "dispute_resolution": {
        "require_formal_process": True,
        "description": (
            "A formal dispute-resolution process should be specified."
        ),
    },
    "termination": {
        "require_clause": True,
        "description": (
            "Termination rights, conditions, and notice requirements "
            "should be specified."
        ),
    },
    "warranties": {
        "require_clause": True,
        "description": (
            "Representations and warranties should be clearly specified."
        ),
    },
    "indemnity": {
        "require_clause": True,
        "description": (
            "Indemnification obligations should be clearly specified."
        ),
    },
    "governing_law": {
        "require_clause": True,
        "description": (
            "The governing law should be identified."
        ),
    },
    "force_majeure": {
        "require_clause": True,
        "description": (
            "Force majeure conditions and their effect should be specified."
        ),
    },
    "service_availability": {
        "require_uptime_target": True,
        "description": (
            "Service availability should include a measurable "
            "uptime or service-level target."
        ),
    },
    "data_protection": {
        "require_data_protection": True,
        "description": (
            "Data handling should specify permitted use and "
            "appropriate data-protection requirements."
        ),
    },
    "security_incident": {
        "require_notification_deadline": True,
        "description": (
            "Security incident notification should include "
            "a defined reporting deadline."
        ),
    },
}


# Keywords used to locate candidate evidence in the uploaded policy.
# These matches are preliminary and must be verified by a human.
EVIDENCE_KEYWORDS = {
    "payment_terms": [
        "payment", "invoice", "payable", "days", "paid",
    ],
    "confidentiality": [
        "confidential", "confidentiality", "disclosure",
    ],
    "liability": [
        "liability", "liable", "damages", "cap",
    ],
    "intellectual_property": [
        "intellectual property", "ownership", "copyright",
        "ip rights",
    ],
    "dispute_resolution": [
        "dispute", "arbitration", "mediation", "jurisdiction",
    ],
    "termination": ["termination", "terminate", "notice period"],
    "warranties": ["warranty", "warranties", "representation"],
    "indemnity": ["indemnity", "indemnification", "indemnify"],
    "governing_law": ["governing law", "applicable law", "jurisdiction"],
    "force_majeure": ["force majeure", "events beyond control"],
    "service_availability": [
        "service availability",
        "uptime",
        "service level",
        "availability target",
        "sla",
    ],
    "data_protection": [
        "data protection",
        "data handling",
        "personal data",
        "customer data",
        "authorized use",
        "access control",
        "encryption",
    ],
    "security_incident": [
        "security incident",
        "incident notification",
        "notify within",
        "notification deadline",
        "72 hours",
        "24 hours",
    ],
}


def compare_with_policy(
    clauses: list[dict],
    policy: dict | None = None,
    policy_evidence: list[dict] | None = None,
) -> list[dict]:
    """
    Compare extracted contract clauses against policy rules.

    policy_evidence contains candidate requirements extracted
    from the uploaded policy, including text and source locations.

    All results are preliminary and require human review.
    They are not legal conclusions.
    """
    active_policy = policy if policy is not None else DEFAULT_POLICY
    candidates = policy_evidence or []

    results = []
    clauses_by_category = {}

    for clause in clauses:
        category = clause.get("category", "other")
        clauses_by_category.setdefault(category, []).append(clause)

    def find_policy_evidence(category: str) -> dict:
        """
        Select a relevant policy evidence candidate.

        Prefer substantive requirements over short headings.
        This is a keyword-based heuristic, not semantic verification.
        """
        keywords = EVIDENCE_KEYWORDS.get(category, [])
        matching_candidates = []

        requirement_phrases = (
            "must",
            "should",
            "shall",
            "required",
            "within",
            "at least",
            "not exceed",
            "specify",
            "specified",
            "documented",
            "protected",
        )

        for index, candidate in enumerate(candidates):
            candidate_category = candidate.get("category")

            if candidate_category not in (None, category):
                continue

            candidate_text = candidate.get("text", "").strip()

            if not candidate_text:
                continue

            normalized_text = candidate_text.lower()

            matched_keywords = [
                keyword
                for keyword in keywords
                if keyword in normalized_text
            ]

            if not matched_keywords:
                continue

            # Start with keyword relevance.
            score = len(matched_keywords) * 10

            # Prefer substantive sentences to short headings.
            word_count = len(candidate_text.split())

            if word_count >= 5:
                score += 5

            if word_count >= 8:
                score += 3

            # Prefer wording that expresses a requirement.
            if any(
                phrase in normalized_text
                for phrase in requirement_phrases
            ):
                score += 10

            score += int(
                float(candidate.get("retrieval_score", 0)) * 100
            )

            matching_candidates.append(
                (score, index, candidate)
            )

        if not matching_candidates:
            return {}

        # Highest score first; retain document order for ties.
        matching_candidates.sort(
            key=lambda item: (-item[0], item[1])
        )

        return matching_candidates[0][2]

    def add_result(
        category: str,
        requirement: str,
        status: str,
        explanation: str,
        evidence: str = "",
        source_locations: list | None = None,
    ):
        contract_locations = source_locations or []

        # Find the contract clause associated with this result.
        matched_clause = next(
            (
                clause
                for clause in clauses_by_category.get(category, [])
                if clause.get("source_locations", [])
                == contract_locations
            ),
            {},
        )

        # Locate candidate evidence in the uploaded policy.
        policy_item = find_policy_evidence(category)
        policy_source = policy_item.get("source_location")

        results.append({
            "category": category,
            "policy_requirement": requirement,
            "status": status,
            "explanation": explanation,
            "evidence": evidence,
            "source_locations": contract_locations,
            "review_status": "pending",

            # Contract traceability.
            "contract_requirement": matched_clause.get(
                "clause_text", ""
            ),

            # Uploaded policy traceability.
            "policy_evidence": policy_item.get("text", ""),
            "policy_source_locations": (
                [policy_source] if policy_source else []
            ),

            # Explain the detected difference.
            "difference": explanation,

            # Candidate evidence still needs human verification.
            "policy_evidence_review_status": (
                policy_item.get("review_status", "pending")
                if policy_item
                else "not_found"
            ),
        })

    for category, rules in active_policy.items():
        matching_clauses = clauses_by_category.get(category, [])

        if not matching_clauses:
            add_result(
                category,
                rules.get("description", "Required clause"),
                "missing_clause",
                "No clause in this category was identified. "
                "Confirm whether the policy requires one.",
            )
            continue

        for clause in matching_clauses:
            text = clause.get("clause_text", "").strip()
            normalized = text.lower()
            locations = clause.get("source_locations", [])

            requirement = rules.get(
                "description",
                "Review this clause against policy.",
            )

            # 1. Payment terms
            if category == "payment_terms":
                max_days = rules.get("max_payment_days")

                if max_days is None:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "No numeric payment limit is configured.",
                        text,
                        locations,
                    )
                    continue

                match = re.search(
                    r"\b(\d{1,3})\s+days?\b",
                    normalized,
                )

                if not match:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "A numeric payment period was not detected.",
                        text,
                        locations,
                    )
                    continue

                days = int(match.group(1))

                if days > max_days:
                    add_result(
                        category,
                        requirement,
                        "deviation_detected",
                        f"The contract specifies {days} days, "
                        f"exceeding the policy limit of "
                        f"{max_days} days.",
                        match.group(0),
                        locations,
                    )
                else:
                    add_result(
                        category,
                        requirement,
                        "no_deviation_detected",
                        "The detected payment period is within "
                        "the configured policy limit.",
                        match.group(0),
                        locations,
                    )

            # 2. Confidentiality
            elif category == "confidentiality":
                required_years = rules.get(
                    "minimum_duration_years"
                )

                duration_match = re.search(
                    r"\bfor\s+(\d{1,2})\s+years?\s+"
                    r"(?:after|following)\s+termination\b",
                    normalized,
                )

                if not duration_match:
                    duration_match = re.search(
                        r"\b(\d{1,2})\s+years?\s+"
                        r"(?:after|following)\s+termination\b",
                        normalized,
                    )

                perpetual = any(
                    term in normalized
                    for term in ("perpetual", "indefinitely")
                )

                if perpetual:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "The clause appears to specify an indefinite "
                        "duration. Confirm how this satisfies the "
                        "reference policy.",
                        text,
                        locations,
                    )

                elif duration_match:
                    actual_years = int(duration_match.group(1))

                    if (
                        required_years is not None
                        and actual_years < required_years
                    ):
                        add_result(
                            category,
                            requirement,
                            "deviation_detected",
                            f"The contract specifies {actual_years} "
                            f"years, below the configured policy "
                            f"duration of {required_years} years.",
                            duration_match.group(0),
                            locations,
                        )

                    elif required_years is not None:
                        add_result(
                            category,
                            requirement,
                            "no_deviation_detected",
                            "The detected duration meets or exceeds "
                            "the configured policy duration.",
                            duration_match.group(0),
                            locations,
                        )

                    else:
                        add_result(
                            category,
                            requirement,
                            "no_deviation_detected",
                            "An explicit duration was detected. "
                            "No minimum duration is configured, so "
                            "the comparison remains limited.",
                            duration_match.group(0),
                            locations,
                        )

                elif rules.get("require_duration"):
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "An explicit confidentiality duration was "
                        "not detected. Manual review is required.",
                        text,
                        locations,
                    )

                else:
                    add_result(
                        category,
                        requirement,
                        "no_deviation_detected",
                        "No mandatory duration check is configured.",
                        text,
                        locations,
                    )

            # 3. Liability

            elif category == "liability":
                cap_terms = [
                    "cap",
                    "capped",
                    "shall not exceed",
                    "maximum aggregate liability",
                    "limited to",
                ]

                missing_cap_terms = [
                    "does not specify a liability cap",
                    "does not specify a cap",
                    "no liability cap",
                    "no cap",
                    "without a liability cap",
                    "liability cap is not specified",
                    "liability cap has not been specified",
                    "does not include a liability cap",
                    "does not state a liability cap",
                ]

                explicitly_missing_cap = any(
                    term in normalized
                    for term in missing_cap_terms
                )

                has_cap = any(
                    term in normalized
                    for term in cap_terms
                )

                if (
                    rules.get("require_explicit_cap")
                    and explicitly_missing_cap
                ):
                    add_result(
                        category,
                        requirement,
                        "deviation_detected",
                        "The contract explicitly states that a "
                        "liability cap is not specified, while the "
                        "inferred policy rule requires one. Confirm "
                        "the draft policy requirement before "
                        "finalizing this finding.",
                        text,
                        locations,
                    )

                elif (
                    rules.get("require_explicit_cap")
                    and not has_cap
                ):
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "An explicit liability cap was not "
                        "detected. Manual review is required.",
                        text,
                        locations,
                    )

                else:
                    add_result(
                        category,
                        requirement,
                        "no_deviation_detected",
                        "Liability cap wording was detected. "
                        "Confirm the cap's meaning and adequacy "
                        "through human review.",
                        text,
                        locations,
                    )

            # 4. Intellectual property
            elif category == "intellectual_property":
                deferred_terms = [
                    "separate written agreement",
                    "to be agreed",
                    "will be determined separately",
                    "subject to a separate agreement",
                ]

                ownership_deferred = any(
                    term in normalized for term in deferred_terms
                )

                if (
                    rules.get("require_explicit_ownership")
                    and ownership_deferred
                ):
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "The clause appears to defer ownership details "
                        "to a separate agreement.",
                        text,
                        locations,
                    )
                else:
                    add_result(
                        category,
                        requirement,
                        "no_deviation_detected",
                        "No configured ownership deferral pattern "
                        "was detected.",
                        text,
                        locations,
                    )

            # 5. Dispute resolution
            elif category == "dispute_resolution":
                formal_terms = [
                    "arbitration",
                    "court",
                    "jurisdiction",
                    "mediation",
                    "venue",
                ]

                has_formal_process = any(
                    term in normalized for term in formal_terms
                )

                if (
                    rules.get("require_formal_process")
                    and not has_formal_process
                ):
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "A formal dispute-resolution mechanism "
                        "was not detected.",
                        text,
                        locations,
                    )
                else:
                    add_result(
                        category,
                        requirement,
                        "no_deviation_detected",
                        "The configured dispute-resolution wording "
                        "check passed.",
                        text,
                        locations,
                    )


            # 6. Service availability
            elif category == "service_availability":
                uptime_match = re.search(
                    r"\b(\d{2,3}(?:\.\d+)?)\s*%\s*"
                    r"(?:uptime|availability)\b",
                    normalized,
                )

                required_uptime = rules.get(
                    "minimum_uptime_percent"
                )

                if not uptime_match:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "A numeric uptime or availability percentage "
                        "was not detected.",
                        text,
                        locations,
                    )
                elif required_uptime is None:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "A numeric uptime percentage was detected, "
                        "but the policy has no numeric uptime threshold.",
                        uptime_match.group(0),
                        locations,
                    )
                else:
                    actual_uptime = float(uptime_match.group(1))

                    if actual_uptime < float(required_uptime):
                        status = "deviation_detected"
                        explanation = (
                            f"The contract specifies {actual_uptime}% "
                            f"uptime, below the policy target of "
                            f"{required_uptime}%."
                        )
                    else:
                        status = "no_deviation_detected"
                        explanation = (
                            f"The detected uptime of {actual_uptime}% "
                            f"meets or exceeds the policy target of "
                            f"{required_uptime}%."
                        )

                    add_result(
                        category,
                        requirement,
                        status,
                        explanation,
                        uptime_match.group(0),
                        locations,
                    )


            # 7. Data protection
            elif category == "data_protection":
                missing_data_terms = [
                    "does not specify data protection",
                    "does not specify data handling",
                    "no data protection",
                    "no data handling requirements",
                    "data protection requirements are not specified",
                ]

                protection_terms = [
                    "data protection",
                    "personal data",
                    "authorized use",
                    "authorised use",
                    "access control",
                    "encryption",
                    "confidential",
                    "only for the purpose",
                ]

                explicitly_missing = any(
                    term in normalized
                    for term in missing_data_terms
                )

                has_protection = any(
                    term in normalized
                    for term in protection_terms
                )

                if explicitly_missing or not has_protection:
                    explanation = (
                        "Adequate data-protection requirements "
                        "were not detected. Manual review is "
                        "required."
                    )
                else:
                    explanation = (
                        "Data-protection wording was detected. "
                        "Verify permitted use, access controls, "
                        "retention, and security requirements "
                        "against the uploaded policy."
                    )

                add_result(
                    category,
                    requirement,
                    "needs_review",
                    explanation,
                    text,
                    locations,
                )


            # 8. Security incident notification
            elif category == "security_incident":
                deadline_match = re.search(
                  r"\b(?:within|no later than|not later than|"
                  r"at most|maximum of|up to)\s+"
                  r"(\d{1,3})\s*(hours?|days?)\b",
                  normalized,
                )



                required_hours = rules.get(
                    "max_notification_hours"
                )

                if not deadline_match:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "A clear security-incident notification "
                        "deadline was not detected.",
                        text,
                        locations,
                    )
                elif required_hours is None:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "A notification deadline was detected, "
                        "but the policy has no numeric deadline "
                        "to compare against.",
                        deadline_match.group(0),
                        locations,
                    )
                else:
                    actual_value = int(deadline_match.group(1))
                    actual_unit = deadline_match.group(2)

                    actual_hours = (
                        actual_value * 24
                        if actual_unit.startswith("day")
                        else actual_value
                    )

                    if actual_hours > int(required_hours):
                        status = "deviation_detected"
                        explanation = (
                            f"The contract allows {actual_hours} hours "
                            f"for notification, exceeding the policy "
                            f"limit of {required_hours} hours."
                        )
                    else:
                        status = "no_deviation_detected"
                        explanation = (
                            f"The detected notification deadline of "
                            f"{actual_hours} hours meets the policy "
                            f"limit of {required_hours} hours."
                        )

                    add_result(
                        category,
                        requirement,
                        status,
                        explanation,
                        deadline_match.group(0),
                        locations,
                    )

            elif category in {
                "termination",
                "warranties",
                "indemnity",
                "governing_law",
                "force_majeure",
            }:
                explicit_absence = any(
                    phrase in normalized
                    for phrase in (
                        "is not specified",
                        "are not specified",
                        "does not include",
                        "does not specify",
                        "no provision for",
                        "no clause for",
                    )
                )
                if explicit_absence:
                    add_result(
                        category,
                        requirement,
                        "deviation_detected",
                        "The extracted wording explicitly indicates "
                        "that this requirement is absent.",
                        text,
                        locations,
                    )
                else:
                    add_result(
                        category,
                        requirement,
                        "needs_review",
                        "A clause was identified, but its terms require "
                        "human comparison with the reference policy.",
                        text,
                        locations,
                    )

    return results
