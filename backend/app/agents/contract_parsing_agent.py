from backend.app.services.document_parser import extract_text


def run_contract_parsing_agent(file_path: str) -> dict:
    """
    Extract text and source locations from a PDF or DOCX contract.
    """
    return extract_text(file_path)
