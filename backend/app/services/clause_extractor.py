
import re


CLAUSE_CATEGORIES = {
    "parties": [
        "parties",
        "the parties",
    ],
    "agreement": [
        "agreement",
        "general provisions",
    ],
    "payment_terms": [
        "payment terms",
        "payment",
        "fees",
        "invoicing",
    ],
    "confidentiality": [
        "confidentiality",
        "confidential information",
        "non-disclosure",
    ],
    "termination": [
        "termination",
        "term and termination",
    ],
    "liability": [
        "liability",
        "limitation of liability",
    ],
    "warranties": [
        "warranties",
        "warranty",
        "representations",
    ],
    "intellectual_property": [
        "intellectual property",
        "ip rights",
        "ownership",
    ],
    "indemnity": [
        "indemnity",
        "indemnification",
    ],
    "dispute_resolution": [
        "dispute resolution",
        "disputes",
        "arbitration",
    ],
    "governing_law": [
        "governing law",
        "applicable law",
    ],
        "data_protection": [
        "data protection",
        "data handling",
        "personal data",
        "customer data",
        "privacy",
    ],
    "service_availability": [
        "service availability",
        "service level",
        "uptime",
    ],
    "security_incident": [
        "security incident notification",
        "security incident",
        "security incidents",
        "incident notification",
    ],
    "force_majeure": [
        "force majeure",
    ],
}


def classify_clause(heading: str) -> str:
    """Assign a category based on the clause heading."""
    normalized = re.sub(
        r"^\s*(?:(?:section|article)\s+)?\d+(?:\.\d+)*[\s.):\-]*",
        "",
        heading.lower(),
    ).strip(" :-.")

    for category, keywords in CLAUSE_CATEGORIES.items():
        if any(keyword in normalized for keyword in keywords):
            return category

    return "other"


def extract_clauses(sections: list[dict]) -> list[dict]:
    """
    Group document paragraphs into clauses while preserving
    their original page or paragraph locations.
    """
    clauses = []
    current_clause = None

    heading_pattern = re.compile(
        r"^\s*(?:(?:section|article)\s+)?"
        r"\d+(?:\.\d+)*[\s.):\-]+"
        r"([A-Za-z][A-Za-z /&()\-]{1,70})\s*$",
        re.IGNORECASE,
    )

    known_heading_pattern = re.compile(
        r"^\s*(?:"
        r"parties|agreement|general provisions|"
        r"payment terms|payment|fees|invoicing|"
        r"confidentiality|confidential information|non-disclosure|"
        r"termination|term and termination|liability|"
        r"limitation of liability|warranties|warranty|"
        r"representations|intellectual property|ip rights|"
        r"ownership|indemnity|indemnification|dispute resolution|"
        r"disputes|arbitration|governing law|applicable law|"
        r"data protection|data handling|personal data|customer data|"
        r"privacy|service availability|service level|uptime|"
        r"security incident notification|security incident|"
        r"security incidents|incident notification|force majeure"
        r")\s*$",
        re.IGNORECASE,
    )

    def save_current_clause():
        if current_clause is not None:
            current_clause["clause_text"] = "\n".join(
                current_clause.pop("_text_parts")
            ).strip()

            clauses.append(current_clause)

    for section in sections:
        section_text = section.get("text", "").strip()

        if not section_text:
            continue

        for text in section_text.splitlines():
            text = text.strip()

            if not text:
                continue

            # Remove the sample document's ending marker.
            if text.lower() == "end of sample contract":
                continue

            numbered_match = heading_pattern.match(text)
            known_match = known_heading_pattern.match(text)

            is_heading = bool(numbered_match or known_match)

            if is_heading:
                save_current_clause()

                heading = text

                current_clause = {
                    "heading": heading,
                    "category": classify_clause(heading),
                    "source_locations": [
                        section.get("location", "Unknown")
                    ],
                    "_text_parts": [],
                }

            elif current_clause is not None:
                current_clause["_text_parts"].append(text)

                location = section.get("location", "Unknown")

                if location not in current_clause["source_locations"]:
                    current_clause["source_locations"].append(location)

    save_current_clause()

    return clauses
