from backend.app.services.policy_comparator import compare_with_policy


def run_policy_comparison_agent(
    clauses: list[dict],
    policy: dict | None = None,
) -> list[dict]:
    """
    Compare contract clauses against configured reference policies.
    """
    return compare_with_policy(clauses, policy)
