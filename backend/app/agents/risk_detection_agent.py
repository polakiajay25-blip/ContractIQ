from backend.app.services.risk_analyzer import analyze_clause_risks


def run_risk_detection_agent(clauses: list[dict]) -> list[dict]:
    """
    Detect potential risks in extracted contract clauses.
    """
    return analyze_clause_risks(clauses)
