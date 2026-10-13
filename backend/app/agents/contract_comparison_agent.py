from difflib import SequenceMatcher


def run_contract_comparison_agent(
    old_text: str,
    new_text: str,
) -> dict:
    """
    Compare two contract versions and summarize textual changes.
    """
    if not isinstance(old_text, str) or not isinstance(new_text, str):
        raise TypeError("Both contract versions must be strings.")

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    matcher = SequenceMatcher(
        a=old_lines,
        b=new_lines,
        autojunk=False,
    )

    changes = []

    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation == "equal":
            continue

        changes.append({
            "change_type": {
                "insert": "added",
                "delete": "removed",
                "replace": "changed",
            }[operation],
            "old_lines": old_lines[old_start:old_end],
            "new_lines": new_lines[new_start:new_end],
            "old_line_start": old_start + 1 if old_start < old_end else None,
            "old_line_end": old_end if old_start < old_end else None,
            "new_line_start": new_start + 1 if new_start < new_end else None,
            "new_line_end": new_end if new_start < new_end else None,
        })

    return {
        "has_changes": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        "notice": (
            "Textual comparison only; a reviewer should assess "
            "the significance of each change."
        ),
    }
