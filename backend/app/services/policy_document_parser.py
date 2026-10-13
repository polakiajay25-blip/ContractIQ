
from pathlib import Path

from backend.app.services.document_parser import extract_text


def parse_policy_document(file_path: str) -> dict:
    """
    Extract text and source locations from a PDF or DOCX
    reference policy document.

    This function extracts candidate requirements but does not
    automatically convert them into verified policy rules.
    """
    path = Path(file_path)

    if path.suffix.lower() not in {".pdf", ".docx"}:
        raise ValueError(
            "Unsupported policy format. Upload a PDF or DOCX file."
        )

    parsed = extract_text(str(path))

    candidate_requirements = []

    for section in parsed.get("sections", []):
        section_text = section.get("text", "").strip()

        if not section_text:
            continue

        # Keep each non-empty line as a reviewable candidate.
        for line in section_text.splitlines():
            requirement_text = line.strip()

            if len(requirement_text) < 10:
                continue

            candidate_requirements.append({
                "text": requirement_text,
                "source_location": section.get(
                    "location", "Unknown location"
                ),
                "review_status": "pending",
            })

    return {
        "filename": parsed.get("filename", path.name),
        "file_type": parsed.get("file_type"),
        "section_count": parsed.get("section_count", 0),
        "full_text": parsed.get("full_text", ""),
        "candidate_requirements": candidate_requirements,
        "candidate_count": len(candidate_requirements),
        "notice": (
            "Extracted text may contain non-policy content. "
            "Candidate requirements require validation before "
            "being used for contract comparisons."
        ),
    }
