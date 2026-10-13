from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END

from backend.app.agents.clause_classification_agent import (
    run_clause_classification_agent,
)
from backend.app.agents.risk_detection_agent import (
    run_risk_detection_agent,
)
from backend.app.agents.policy_comparison_agent import (
    run_policy_comparison_agent,
)
from backend.app.agents.decision_reviewer_agent import (
    run_decision_reviewer_agent,
)


class ContractAnalysisState(TypedDict, total=False):
    sections: list[dict]
    clauses: list[dict]
    findings: list[dict]
    policy_checks: list[dict]
    review: dict[str, Any]
    validation: dict[str, Any]


def extract_clauses_node(state: ContractAnalysisState) -> dict:
    """Agent 2: Extract and classify contract clauses."""
    clauses = run_clause_classification_agent(
        state.get("sections", [])
    )
    return {"clauses": clauses}


def analyze_risks_node(state: ContractAnalysisState) -> dict:
    """Agent 4: Detect potential contract risks."""
    findings = run_risk_detection_agent(
        state.get("clauses", [])
    )
    return {"findings": findings}


def compare_policy_node(state: ContractAnalysisState) -> dict:
    """Agent 3: Compare clauses with the configured policy."""
    policy_checks = run_policy_comparison_agent(
        state.get("clauses", [])
    )
    return {"policy_checks": policy_checks}


def review_results_node(state: ContractAnalysisState) -> dict:
    """Agent 6: Check findings and flag items for human review."""
    review = run_decision_reviewer_agent(
        clauses=state.get("clauses", []),
        risk_findings=state.get("findings", []),
        policy_checks=state.get("policy_checks", []),
    )
    return {"review": review}


def validate_results_node(state: ContractAnalysisState) -> dict:
    """Validate workflow outputs and summarize analysis counts."""
    clauses = state.get("clauses", [])
    findings = state.get("findings", [])
    policy_checks = state.get("policy_checks", [])
    review = state.get("review", {})

    valid = (
        isinstance(clauses, list)
        and isinstance(findings, list)
        and isinstance(policy_checks, list)
        and isinstance(review, dict)
    )

    validation = {
        "status": "completed" if valid else "failed",
        "checks_passed": valid,
        "clause_count": len(clauses),
        "risk_finding_count": len(findings),
        "policy_check_count": len(policy_checks),
        "review_status": review.get("status", "not_run"),
        "human_review_required": review.get(
            "human_review_required", True
        ),
    }

    return {"validation": validation}


def build_contract_workflow():
    """Build the LangGraph contract-analysis workflow."""
    workflow = StateGraph(ContractAnalysisState)

    workflow.add_node("classify_clauses", extract_clauses_node)
    workflow.add_node("detect_risks", analyze_risks_node)
    workflow.add_node("compare_policy", compare_policy_node)
    workflow.add_node("review_results", review_results_node)
    workflow.add_node("validate_results", validate_results_node)

    workflow.add_edge(START, "classify_clauses")
    workflow.add_edge("classify_clauses", "detect_risks")
    workflow.add_edge("detect_risks", "compare_policy")
    workflow.add_edge("compare_policy", "review_results")
    workflow.add_edge("review_results", "validate_results")
    workflow.add_edge("validate_results", END)

    return workflow.compile()


contract_workflow = build_contract_workflow()


def run_contract_workflow(sections: list[dict]) -> dict:
    """Run clause classification, risk, policy, and review agents."""
    return contract_workflow.invoke({
        "sections": sections,
    })