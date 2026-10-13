from io import BytesIO

import fitz
from fastapi.testclient import TestClient
from docx import Document

from backend.app.agents.contract_comparison_agent import (
    run_contract_comparison_agent,
)
import backend.app.main as main_module
from backend.app.main import app
import backend.app.services.auth as auth_module
from backend.app.services.auth import authenticate, validate_access_token
from backend.app.services.policy_retriever import retrieve_policy_evidence
from backend.app.services.review_status import determine_review_status
from backend.app.services.report_generator import generate_analysis_pdf
from backend.app.services.policy_rule_extractor import extract_policy_rules
from backend.app.services.policy_comparator import compare_with_policy
from backend.app.services.review_store import normalize_database_url
from backend.app.services.llm_reviewer import (
    LLMReviewError,
    run_llm_evidence_review,
)


def test_optional_llm_review_keeps_deterministic_results_on_503(
    monkeypatch,
):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    def fail_with_unavailable(**kwargs):
        raise LLMReviewError(
            "Gemini is temporarily unavailable or overloaded.",
            status_code=503,
        )

    monkeypatch.setattr(
        main_module,
        "run_llm_evidence_review",
        fail_with_unavailable,
    )

    result = main_module.run_optional_llm_evidence_review(
        clauses=[],
        risk_findings=[],
        policy_checks=[],
        policy_evidence=[],
        reviewer_items=[{"item_id": "risk:0"}],
    )

    assert result["status"] == "unavailable"
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-test-model"
    assert result["reviewed_count"] == 0
    assert result["not_reviewed_count"] == 1
    assert "temporarily unavailable" in result["notice"]


def test_optional_llm_review_does_not_hide_non_503_errors(monkeypatch):
    def fail_with_forbidden(**kwargs):
        raise LLMReviewError(
            "Invalid Gemini credentials.",
            status_code=403,
        )

    monkeypatch.setattr(
        main_module,
        "run_llm_evidence_review",
        fail_with_forbidden,
    )

    try:
        main_module.run_optional_llm_evidence_review(
            clauses=[],
            risk_findings=[],
            policy_checks=[],
            policy_evidence=[],
            reviewer_items=[],
        )
    except LLMReviewError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Non-503 LLM errors must remain visible.")


def test_postgresql_urls_use_installed_psycopg_driver():
    assert normalize_database_url(
        "postgres://user:pass@host:5432/reviews"
    ) == "postgresql+psycopg://user:pass@host:5432/reviews"
    assert normalize_database_url(
        "postgresql://user:pass@host:5432/reviews"
    ) == "postgresql+psycopg://user:pass@host:5432/reviews"
    assert normalize_database_url(
        "postgresql+psycopg2://user:pass@host:5432/reviews"
    ) == "postgresql+psycopg://user:pass@host:5432/reviews"
    assert normalize_database_url(
        "postgresql+psycopg://user:pass@host:5432/reviews"
    ) == "postgresql+psycopg://user:pass@host:5432/reviews"
    assert normalize_database_url("sqlite:///reviews.db") == (
        "sqlite:///reviews.db"
    )


def test_llm_reviewer_checks_model_quotes_against_source_evidence(
    monkeypatch,
):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "content": (
                        '{"assessments": [{"finding_id": "policy_check:0", '
                        '"verdict": "supported", '
                        '"rationale": "The contract allows 90 days.", '
                        '"contract_quote": "paid within 90 days", '
                        '"policy_quote": "paid within 30 days"}]}'
                    )
                }
            }

    monkeypatch.setattr(
        "backend.app.services.llm_reviewer.httpx.post",
        lambda url, **kwargs: (
            assert_ollama_request(url, kwargs) or FakeResponse()
        ),
    )
    items = [{"item_id": "policy_check:0"}]

    result = run_llm_evidence_review(
        clauses=[{
            "category": "payment_terms",
            "clause_text": "Invoices must be paid within 90 days.",
            "source_locations": ["Paragraph 4"],
        }],
        risk_findings=[],
        policy_checks=[{
            "category": "payment_terms",
            "status": "deviation_detected",
            "contract_requirement": "90 days",
            "policy_evidence": "Invoices should be paid within 30 days.",
        }],
        policy_evidence=[{
            "category": "payment_terms",
            "text": "Invoices should be paid within 30 days.",
            "source_location": "Page 2",
        }],
        reviewer_items=items,
    )

    assert result["status"] == "completed"
    assert result["assessments"][0]["verdict"] == "supported"
    assert result["provider"] == "ollama"
    assert result["assessments"][0]["contract_quote_verified"] is True
    assert result["assessments"][0]["policy_quote_verified"] is True
    assert items[0]["llm_review"]["finding_id"] == "policy_check:0"


def test_llm_reviewer_downgrades_unverified_model_quotes(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "content": (
                        '{"assessments": [{"finding_id": "risk_finding:0", '
                        '"verdict": "supported", '
                        '"rationale": "It is risky.", '
                        '"contract_quote": "Invented clause", '
                        '"policy_quote": null}]}'
                    )
                }
            }

    monkeypatch.setattr(
        "backend.app.services.llm_reviewer.httpx.post",
        lambda url, **kwargs: (
            assert_ollama_request(url, kwargs),
            FakeResponse(),
        )[1],
    )
    result = run_llm_evidence_review(
        clauses=[{
            "category": "payment_terms",
            "clause_text": "Invoices are paid in 90 days.",
            "source_locations": ["Paragraph 1"],
        }],
        risk_findings=[{
            "category": "payment_terms",
            "description": "Long payment period.",
            "evidence": "90 days",
        }],
        policy_checks=[],
        policy_evidence=[],
        reviewer_items=[{"item_id": "risk_finding:0"}],
    )

    assert result["assessments"][0]["verdict"] == "uncertain"
    assert result["assessments"][0]["contract_quote"] is None
    assert result["assessments"][0]["contract_quote_verified"] is False


def test_llm_reviewer_rejects_invalid_model_json(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "not json"}}

    monkeypatch.setattr(
        "backend.app.services.llm_reviewer.httpx.post",
        lambda url, **kwargs: (
            assert_ollama_request(url, kwargs),
            FakeResponse(),
        )[1],
    )

    try:
        run_llm_evidence_review(
            clauses=[],
            risk_findings=[{}],
            policy_checks=[],
            policy_evidence=[],
            reviewer_items=[{"item_id": "risk_finding:0"}],
        )
    except LLMReviewError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("Invalid model JSON must be reported.")


def assert_ollama_request(url: str, kwargs: dict) -> None:
    assert url == "http://127.0.0.1:11434/api/chat"
    assert kwargs["json"]["model"] == "llama3.2"
    assert kwargs["json"]["format"] == "json"
    assert kwargs["json"]["stream"] is False
    assert kwargs["timeout"] == 180.0


def test_gemini_review_uses_api_key_header_and_verifies_quotes(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": (
                                '{"assessments": [{"finding_id": '
                                '"policy_check:0", "verdict": "supported", '
                                '"rationale": "Evidence matches.", '
                                '"contract_quote": "paid within 90 days", '
                                '"policy_quote": "paid within 30 days"}]}'
                            )
                        }]
                    }
                }]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        "backend.app.services.llm_reviewer.httpx.post",
        fake_post,
    )
    items = [{"item_id": "policy_check:0"}]
    result = run_llm_evidence_review(
        clauses=[{
            "category": "payment_terms",
            "clause_text": "Invoices must be paid within 90 days.",
            "source_locations": ["Paragraph 4"],
        }],
        risk_findings=[],
        policy_checks=[{
            "category": "payment_terms",
            "status": "deviation_detected",
            "contract_requirement": "90 days",
            "policy_evidence": "Invoices should be paid within 30 days.",
        }],
        policy_evidence=[{
            "category": "payment_terms",
            "text": "Invoices should be paid within 30 days.",
            "source_location": "Page 2",
        }],
        reviewer_items=items,
    )

    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-test-model:generateContent"
    )
    assert captured["headers"] == {"x-goog-api-key": "test-gemini-key"}
    assert captured["json"]["generationConfig"]["responseMimeType"] == (
        "application/json"
    )
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-test-model"
    assert result["assessments"][0]["verdict"] == "supported"
    assert result["assessments"][0]["contract_quote_verified"] is True
    assert result["assessments"][0]["policy_quote_verified"] is True


def test_gemini_review_is_not_configured_without_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = run_llm_evidence_review(
        clauses=[],
        risk_findings=[],
        policy_checks=[],
        policy_evidence=[],
        reviewer_items=[{"item_id": "risk_finding:0"}],
    )

    assert result["provider"] == "gemini"
    assert result["status"] == "not_configured"
    assert result["not_reviewed_count"] == 1


def test_gemini_quota_error_does_not_leak_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")

    class FakeResponse:
        status_code = 429

        def raise_for_status(self):
            request = httpx.Request(
                "POST",
                "https://generativelanguage.googleapis.com/test",
            )
            response = httpx.Response(
                429,
                request=request,
                text="quota exceeded",
            )
            raise httpx.HTTPStatusError(
                "quota exceeded",
                request=request,
                response=response,
            )

    import httpx

    monkeypatch.setattr(
        "backend.app.services.llm_reviewer.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    try:
        run_llm_evidence_review(
            clauses=[],
            risk_findings=[{}],
            policy_checks=[],
            policy_evidence=[],
            reviewer_items=[{"item_id": "risk_finding:0"}],
        )
    except LLMReviewError as exc:
        assert "quota limit" in str(exc)
        assert "secret-test-key" not in str(exc)
    else:
        raise AssertionError("Gemini quota errors must be reported.")


def test_gemini_unavailable_error_suggests_retry(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    class FakeResponse:
        status_code = 503

        def raise_for_status(self):
            request = httpx.Request(
                "POST",
                "https://generativelanguage.googleapis.com/test",
            )
            response = httpx.Response(
                503,
                request=request,
                text="temporarily unavailable",
            )
            raise httpx.HTTPStatusError(
                "temporarily unavailable",
                request=request,
                response=response,
            )

    import httpx

    monkeypatch.setattr(
        "backend.app.services.llm_reviewer.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    try:
        run_llm_evidence_review(
            clauses=[],
            risk_findings=[{}],
            policy_checks=[],
            policy_evidence=[],
            reviewer_items=[{"item_id": "risk_finding:0"}],
        )
    except LLMReviewError as exc:
        assert "temporarily unavailable" in str(exc)
        assert "try again" in str(exc)
    else:
        raise AssertionError("Gemini availability errors must be reported.")


def create_docx(text: str) -> bytes:
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def test_jwt_authentication_uses_configured_reviewer(monkeypatch):
    monkeypatch.setenv("REVIEWER_USERNAME", "reviewer")
    monkeypatch.setenv("REVIEWER_PASSWORD", "a-long-test-password")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "a-secret-key-long-enough-for-tests-123456",
    )

    token = authenticate("reviewer", "a-long-test-password")

    assert token is not None
    assert validate_access_token(token) == "reviewer"
    assert authenticate("reviewer", "wrong-password") is None


def test_authentication_loads_its_env_file_without_other_service_imports(
    monkeypatch,
    tmp_path,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "REVIEWER_USERNAME=file-reviewer\n"
        "REVIEWER_PASSWORD=file-password\n"
        "JWT_SECRET_KEY=file-secret-long-enough-for-tests-123456\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(auth_module, "AUTH_ENV_PATH", env_file)
    monkeypatch.delenv("REVIEWER_USERNAME", raising=False)
    monkeypatch.delenv("REVIEWER_PASSWORD", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    token = auth_module.authenticate("file-reviewer", "file-password")

    assert token is not None
    assert auth_module.validate_access_token(token) == "file-reviewer"


def test_api_routes_require_jwt_but_health_is_public(monkeypatch, tmp_path):
    monkeypatch.setenv("REVIEWER_USERNAME", "reviewer")
    monkeypatch.setenv("REVIEWER_PASSWORD", "a-long-test-password")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "a-secret-key-long-enough-for-tests-123456",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{(tmp_path / 'reviews.db').as_posix()}",
    )

    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/reviews").status_code == 401

    token_response = client.post(
        "/api/v1/auth/token",
        json={
            "username": "reviewer",
            "password": "a-long-test-password",
        },
    )

    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    assert client.get(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200


def test_contract_version_comparison_reports_changed_line_ranges():
    comparison = run_contract_comparison_agent(
        "Invoices must be paid within 30 days.\nConfidentiality lasts 5 years.",
        "Invoices must be paid within 90 days.\nConfidentiality lasts 5 years.",
    )

    assert comparison["has_changes"] is True
    assert comparison["change_count"] == 1
    assert comparison["changes"][0]["old_lines"] == [
        "Invoices must be paid within 30 days."
    ]
    assert comparison["changes"][0]["new_lines"] == [
        "Invoices must be paid within 90 days."
    ]
    assert comparison["changes"][0]["old_line_start"] == 1
    assert comparison["changes"][0]["new_line_start"] == 1


def test_version_comparison_endpoint_accepts_authenticated_docx(monkeypatch):
    monkeypatch.setenv("REVIEWER_USERNAME", "reviewer")
    monkeypatch.setenv("REVIEWER_PASSWORD", "a-long-test-password")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "a-secret-key-long-enough-for-tests-123456",
    )
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/token",
        json={
            "username": "reviewer",
            "password": "a-long-test-password",
        },
    ).json()["access_token"]

    response = client.post(
        "/api/v1/documents/compare-versions",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "old_contract_file": (
                "old.docx",
                create_docx("Payment is due in 30 days."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "new_contract_file": (
                "new.docx",
                create_docx("Payment is due in 90 days."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["old_filename"] == "old.docx"
    assert body["new_filename"] == "new.docx"
    assert body["change_count"] == 1
    assert body["changes"][0]["old_line_start"] == 1


def test_uploaded_policy_review_returns_traceable_findings(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("REVIEWER_USERNAME", "reviewer")
    monkeypatch.setenv("REVIEWER_PASSWORD", "a-long-test-password")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "a-secret-key-long-enough-for-tests-123456",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{(tmp_path / 'reviews.db').as_posix()}",
    )
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(
        main_module,
        "run_llm_evidence_review",
        lambda **kwargs: {
            "status": "not_configured",
            "provider": "disabled",
            "model": "llama3.2",
            "reviewed_count": 0,
            "not_reviewed_count": len(kwargs["reviewer_items"]),
            "assessments": [],
        },
    )
    def fake_retrieve(candidates, queries):
        assert "payment_terms" in queries
        return [
            {
                **candidate,
                "category": "payment_terms",
                "retrieval_score": 0.95,
            }
            for candidate in candidates
        ]

    monkeypatch.setattr(
        main_module,
        "retrieve_policy_evidence",
        fake_retrieve,
    )
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/token",
        json={
            "username": "reviewer",
            "password": "a-long-test-password",
        },
    ).json()["access_token"]

    response = client.post(
        "/api/v1/documents/compare-uploaded-policy",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "contract_file": (
                "contract.docx",
                create_docx(
                    "1. Payment Terms\n"
                    "Invoices must be paid within 90 days."
                ),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "policy_file": (
                "policy.docx",
                create_docx("Invoices must be paid within 30 days."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reviewer_result"]["llm_review"]["provider"] == "disabled"
    payment_check = next(
        item
        for item in body["policy_checks"]
        if item["category"] == "payment_terms"
    )
    assert body["review_status"] == "attention_required"
    assert payment_check["status"] == "deviation_detected"
    assert payment_check["contract_requirement"]
    assert "30 days" in payment_check["policy_evidence"]
    assert payment_check["source_locations"]
    assert payment_check["policy_source_locations"]


def test_review_status_distinguishes_unresolved_from_confirmed_deviation():
    assert determine_review_status(
        [{"status": "needs_review"}],
        [],
    ) == "human_review_required"
    assert determine_review_status(
        [{"status": "deviation_detected"}],
        [],
    ) == "attention_required"
    assert determine_review_status(
        [{"status": "no_deviation_detected"}],
        [],
    ) == "no_major_deviation"
    assert determine_review_status([], []) == "human_review_required"


def test_policy_retrieval_returns_semantically_relevant_source(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    class FakeEmbeddingModel:
        def encode(self, texts, **kwargs):
            assert kwargs["normalize_embeddings"] is True
            return [
                [1.0, 0.0]
                if "invoice" in text.lower() or "payment" in text.lower()
                else [0.0, 1.0]
                for text in texts
            ]

    def fake_model_loader(model_name: str):
        assert model_name
        return FakeEmbeddingModel()

    monkeypatch.setattr(
        "backend.app.services.policy_retriever._load_embedding_model",
        fake_model_loader,
    )

    retrieved = retrieve_policy_evidence(
        [
            {
                "text": "Invoices must be paid within 30 days.",
                "source_location": "Page 2",
            },
            {
                "text": "Confidential information is protected.",
                "source_location": "Page 5",
            },
        ],
        {"payment_terms": "invoice payment deadline"},
        top_k=1,
    )

    assert len(retrieved) == 1
    assert retrieved[0]["source_location"] == "Page 2"
    assert retrieved[0]["category"] == "payment_terms"
    assert retrieved[0]["retrieval_score"] > 0.9


def test_qualitative_policy_categories_are_sent_to_human_review():
    extracted = extract_policy_rules(
        "Indemnification must cover third-party claims. "
        "The agreement shall state termination rights. "
        "Governing law must be specified."
    )
    rules = extracted["rules"]

    assert "indemnity" in rules
    assert "termination" in rules
    assert "governing_law" in rules

    result = compare_with_policy(
        [
            {
                "category": "indemnity",
                "heading": "Indemnity",
                "clause_text": (
                    "The supplier will indemnify the customer."
                ),
                "source_locations": ["Paragraph 9"],
            }
        ],
        policy=rules,
    )

    indemnity_check = next(
        item for item in result if item["category"] == "indemnity"
    )
    assert indemnity_check["status"] == "needs_review"
    assert indemnity_check["source_locations"] == ["Paragraph 9"]


def test_pdf_report_generation_includes_review_status():
    pdf = generate_analysis_pdf(
        filename="contract.docx",
        document={"file_type": "docx", "section_count": 1},
        summary={
            "total_clauses": 1,
            "total_risk_findings": 0,
            "total_policy_checks": 1,
            "review_status": "no_major_deviation",
            "reviewer_result": {
                "status": "review_required",
                "llm_review": {
                    "status": "completed",
                    "model": "llama3.2",
                    "reviewed_count": 1,
                    "not_reviewed_count": 0,
                },
                "items": [{
                    "item": "payment_terms",
                    "item_type": "policy_check",
                    "llm_review": {
                        "verdict": "supported",
                        "rationale": "The quoted days match.",
                        "contract_quote": "paid within 90 days",
                        "contract_quote_verified": True,
                        "policy_quote": "paid within 30 days",
                        "policy_quote_verified": True,
                    },
                }],
            },
        },
        clauses=[],
        findings=[],
        policy_checks=[],
    )

    assert pdf.getvalue().startswith(b"%PDF")
    document = fitz.open(stream=pdf.getvalue(), filetype="pdf")
    report_text = "\n".join(page.get_text() for page in document)
    assert "LLM evidence review status" in report_text
    assert "LLM assessment" in report_text
    assert "paid within 90 days" in report_text
