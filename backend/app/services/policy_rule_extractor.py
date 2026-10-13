
import re


def _to_hours(value: int, unit: str) -> int:
    """Convert a duration expressed in days or hours to hours."""
    return value * 24 if unit.lower().startswith("day") else value


def _find_relevant_sentence(
    text: str,
    keywords: tuple[str, ...],
) -> str:
    """Find the first sentence containing one of the supplied keywords."""
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)

    for sentence in sentences:
        if any(keyword in sentence for keyword in keywords):
            return sentence.strip()

    return ""


def extract_policy_rules(policy_text: str) -> dict:
    """
    Extract draft rules from an uploaded reference policy.

    Rules are inferred from text patterns and must be verified
    against the original policy by an authorized reviewer.
    """
    text = policy_text.lower()
    rules = {}

    # 1. Payment terms
    payment_keywords = ("invoice", "payment", "paid", "payable")
    payment_sentence = _find_relevant_sentence(
        text, payment_keywords
    )

    if payment_sentence:
        payment_patterns = (
            r"\b(?:within|maximum of|up to|not exceed(?:ing)?|"
            r"no more than|at most)\s+(\d{1,3})\s+days?\b",
            r"\bpayment terms?\s*(?:of|:)?\s*"
            r"(\d{1,3})\s+days?\b",
        )

        payment_match = None

        for pattern in payment_patterns:
            payment_match = re.search(pattern, payment_sentence)
            if payment_match:
                break

        if payment_match:
            days = int(payment_match.group(1))
            rules["payment_terms"] = {
                "max_payment_days": days,
                "description": (
                    f"Invoices should be paid within {days} days."
                ),
            }

    # 2. Confidentiality duration
    if "confidential" in text or "confidentiality" in text:
        confidentiality_rule = {
            "require_duration": True,
            "description": (
                "The confidentiality duration should be specified."
            ),
        }

        duration_match = re.search(
            r"\b(?:for\s+)?(\d{1,2})\s+years?\s+"
            r"(?:after|following)\s+termination\b",
            text,
        )

        if duration_match:
            years = int(duration_match.group(1))
            confidentiality_rule["minimum_duration_years"] = years
            confidentiality_rule["description"] = (
                "Confidential information must remain protected "
                f"for at least {years} years after termination."
            )

        rules["confidentiality"] = confidentiality_rule

    # 3. Liability
    if "liability" in text:
        cap_required = any(
            phrase in text
            for phrase in (
                "maximum aggregate liability",
                "liability cap",
                "liability limit",
                "liability limits",
                "liability shall be capped",
                "liability must be capped",
            )
        )

        if cap_required:
            rules["liability"] = {
                "require_explicit_cap": True,
                "description": (
                    "The contract must clearly specify "
                    "the maximum aggregate liability."
                ),
            }

    # 4. Intellectual property
    if (
        "intellectual property" in text
        or "intellectual-property" in text
    ):
        ownership_required = any(
            phrase in text
            for phrase in (
                "ownership",
                "owner",
                "explicitly documented",
                "must be documented",
            )
        )

        if ownership_required:
            rules["intellectual_property"] = {
                "require_explicit_ownership": True,
                "description": (
                    "Intellectual-property ownership must be "
                    "explicitly documented."
                ),
            }

    # 5. Dispute resolution
    if "dispute" in text:
        formal_process_required = any(
            phrase in text
            for phrase in (
                "formal dispute-resolution process",
                "formal dispute resolution process",
                "must specify a formal",
                "must include a formal",
                "must establish a formal",
            )
        )

        if formal_process_required:
            rules["dispute_resolution"] = {
                "require_formal_process": True,
                "description": (
                    "The agreement must specify a formal "
                    "dispute-resolution process."
                ),
            }

    # 6. Service availability / uptime
    availability_keywords = (
        "service availability",
        "uptime",
        "service level",
        "sla",
    )

    if any(term in text for term in availability_keywords):
        availability_rule = {
            "require_uptime_target": True,
            "description": (
                "Service availability should include a measurable "
                "uptime or service-level target."
            ),
        }

        availability_sentence = _find_relevant_sentence(
            text,
            availability_keywords,
        )

        # Supports:
        # "99.9% uptime"
        # "99.9% availability"
        # "minimum availability of 99.9%"
        # "uptime must be at least 99.9%"
        # "Minimum service availability is 99.9%"
        # "Service availability must be at least 99.9%"
        uptime_patterns = (
            # Percentage before uptime or availability.
            r"\b(\d{1,3}(?:\.\d+)?)\s*%\s*"
            r"(?:monthly\s+|annual\s+|yearly\s+)?"
            r"(?:service\s+)?(?:uptime|availability)\b",
            # Minimum/at least service availability is 99.9%.
            r"\b(?:minimum|min(?:imum)?|at least)\s+"
            r"(?:service\s+)?(?:availability|uptime)\s*"
            r"(?:of|is|must be|should be|at least)?\s*"
            r"(\d{1,3}(?:\.\d+)?)\s*%",

            # Availability must be at least 99.9%.
            r"\b(?:uptime|availability)\b"
            r"[^.!?]{0,60}?"
            r"\b(?:at least|minimum of|of)\s+"
            r"(\d{1,3}(?:\.\d+)?)\s*%",

            # A minimum target of 99.9%.
            r"\b(?:minimum|min(?:imum)?|target of)\s+"
            r"(\d{1,3}(?:\.\d+)?)\s*%"
            r"(?!\s*\w)",
        )

        uptime_match = None

        for pattern in uptime_patterns:
            uptime_match = re.search(
                pattern, availability_sentence
            )
            if uptime_match:
                break

        if uptime_match:
            uptime = float(uptime_match.group(1))

            if 0 < uptime <= 100:
                availability_rule["minimum_uptime_percent"] = uptime
                availability_rule["description"] = (
                    f"Service uptime should be at least {uptime}%."
                )

        rules["service_availability"] = availability_rule

    # 7. Data protection
    if any(
        term in text
        for term in (
            "data protection",
            "data handling",
            "personal data",
            "customer data",
        )
    ):
        rules["data_protection"] = {
            "require_data_protection": True,
            "description": (
                "Data handling should specify permitted use and "
                "appropriate data-protection requirements."
            ),
        }

    # 8. Security incident notification
    incident_keywords = (
        "security incident",
        "incident notification",
        "breach notification",
    )

    if any(term in text for term in incident_keywords):
        incident_rule = {
            "require_notification_deadline": True,
            "description": (
                "Security incident notification should include "
                "a defined reporting deadline."
            ),
        }

        incident_sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
            if any(term in sentence for term in incident_keywords)
        ]

        deadline_pattern = (
            r"\b(?:within|no later than|not later than|"
            r"at most|maximum of|up to)\s+"
            r"(\d{1,3})\s*(hours?|days?)\b"
        )

        deadline_match = None

        for sentence in incident_sentences:
            deadline_match = re.search(
                deadline_pattern, sentence
            )
            if deadline_match:
                break

        if deadline_match:
            value = int(deadline_match.group(1))
            unit = deadline_match.group(2)
            deadline_hours = _to_hours(value, unit)

            incident_rule["max_notification_hours"] = deadline_hours
            incident_rule["description"] = (
                "Security incidents must be reported within "
                f"{deadline_hours} hours."
            )

        rules["security_incident"] = incident_rule

    # 9. Presence-based clause requirements. Their meaning still needs
    # an authorized reviewer; this detects coverage, not adequacy.
    category_terms = {
        "termination": ("termination", "terminate"),
        "warranties": ("warranty", "warranties", "representations"),
        "indemnity": ("indemnity", "indemnification", "indemnify"),
        "governing_law": ("governing law", "applicable law"),
        "force_majeure": ("force majeure",),
    }
    requirement_pattern = re.compile(
        r"\b(must|shall|should|required|requires|require)\b"
    )

    for category, keywords in category_terms.items():
        relevant_sentence = _find_relevant_sentence(text, keywords)

        if relevant_sentence and requirement_pattern.search(
            relevant_sentence
        ):
            rules[category] = {
                "require_clause": True,
                "description": relevant_sentence,
            }

    return {
        "rules": rules,
        "review_status": "pending",
        "notice": (
            "Rules are inferred from policy text using predefined "
            "text patterns. Review each rule against the original "
            "policy before use. This system does not provide legal advice."
        ),
    }
