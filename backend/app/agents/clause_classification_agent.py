from backend.app.services.clause_extractor import extract_clauses


def run_clause_classification_agent(sections: list[dict]) -> list[dict]:
    """
    Extract and categorize contract clauses from parsed sections.
    """
    return extract_clauses(sections)
