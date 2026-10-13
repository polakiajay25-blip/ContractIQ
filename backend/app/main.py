
from pathlib import Path
from uuid import uuid4
from typing import Any, Literal
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from backend.app.agents.contract_comparison_agent import (
    run_contract_comparison_agent,
)
from backend.app.services.auth import (
    authenticate,
    get_access_token_lifetime,
    validate_access_token,
)
from backend.app.services.document_parser import extract_text
from backend.app.services.policy_document_parser import parse_policy_document
from backend.app.services.clause_extractor import extract_clauses
from backend.app.services.risk_analyzer import analyze_clause_risks
from backend.app.services.policy_comparator import compare_with_policy
from backend.app.services.policy_retriever import retrieve_policy_evidence
from backend.app.services.report_generator import generate_analysis_pdf
from backend.app.services.policy_rule_extractor import extract_policy_rules
from backend.app.services.review_status import determine_review_status
from backend.app.agents.decision_reviewer_agent import run_decision_reviewer_agent
from backend.app.services.contract_workflow import run_contract_workflow

from backend.app.services.review_store import (
    create_review_session,
    get_review_session,
    list_review_sessions,
    save_review_decision,
)
from backend.app.services.llm_reviewer import (
    LLMReviewError,
    run_llm_evidence_review,
)


def run_optional_llm_evidence_review(
    clauses: list[dict],
    risk_findings: list[dict],
    policy_checks: list[dict],
    policy_evidence: list[dict],
    reviewer_items: list[dict],
) -> dict[str, Any]:
    try:
        return run_llm_evidence_review(
            clauses=clauses,
            risk_findings=risk_findings,
            policy_checks=policy_checks,
            policy_evidence=policy_evidence,
            reviewer_items=reviewer_items,
        )
    except LLMReviewError as exc:
        if exc.status_code != 503:
            raise

        provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
        model = (
            os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
            or "gemini-3.8-flash"
        )
        if provider == "ollama":
            model = os.getenv("OLLAMA_MODEL", "llama3.2").strip() or "llama3.2"

        return {
            "status": "unavailable",
            "provider": provider,
            "model": model,
            "reviewed_count": 0,
            "not_reviewed_count": len(reviewer_items),
            "assessments": [],
            "notice": (
                f"{provider.title()} evidence review is temporarily "
                f"unavailable: {exc} Deterministic findings are still "
                "available and require human review."
            ),
        }


class ReviewDecisionRequest(BaseModel):
    decision: Literal[
        "accepted",
        "rejected",
        "needs_further_review",
    ]
    comment: str | None = Field(default=None, max_length=2000)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


app = FastAPI(
    title="Agentic AI Contract Review & Risk Identification System",
    description=(
        "An AI-assisted system for contract analysis, "
        "policy comparison, and risk identification. "
        "Findings require appropriate human review."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:5174,http://127.0.0.1:5174",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_authentication(request, call_next):
    if (
        request.url.path.startswith("/api/v1/")
        and request.url.path != "/api/v1/auth/token"
        and request.method != "OPTIONS"
    ):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")

        if scheme.lower() != "bearer" or not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "A valid bearer token is required."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            subject = validate_access_token(token)
        except RuntimeError as exc:
            return JSONResponse(
                status_code=503,
                content={"detail": str(exc)},
            )

        if subject is None or subject != os.getenv(
            "REVIEWER_USERNAME", ""
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "The access token is invalid or expired."},
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await call_next(request)


# Upload configuration
UPLOAD_DIR = Path("data/uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@app.post("/api/v1/auth/token")
def issue_access_token(payload: LoginRequest):
    try:
        token = authenticate(payload.username, payload.password)
        lifetime = get_access_token_lifetime()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": lifetime,
    }


# Home endpoint
@app.get("/")
def root():
    return {
        "message": "Contract Review System API is running",
        "documentation": "/docs",
    }


# Health check endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "Contract Review System",
    }


# Upload and parse a reference policy document
@app.post("/api/v1/policies/parse")
async def parse_policy(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX policy files are supported.",
        )

    temporary_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

    try:
        total_size = 0

        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded policy file is empty.",
            )

        try:
            result = parse_policy_document(str(temporary_path))
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Could not read the policy document. "
                    "Check that it is a valid PDF or DOCX file."
                ),
            ) from exc

        return {
            "message": "Policy document parsed successfully.",
            "filename": original_name,
            "file_type": result["file_type"],
            "section_count": result["section_count"],
            "candidate_count": result["candidate_count"],
            "candidate_requirements": result[
                "candidate_requirements"
            ],
            "notice": result["notice"],
        }

    finally:
        await file.close()

        if temporary_path.exists():
            temporary_path.unlink()


# Compare a contract against an uploaded reference policy
@app.post("/api/v1/documents/compare-uploaded-policy")
async def compare_uploaded_policy(
    contract_file: UploadFile = File(...),
    policy_file: UploadFile = File(...),
):
    uploads = [contract_file, policy_file]
    temporary_paths = []

    contract_filename = Path(
        contract_file.filename or ""
    ).name
    policy_filename = Path(
        policy_file.filename or ""
    ).name

    try:
        # Validate both file types before saving either file.
        for upload in uploads:
            filename = Path(upload.filename or "").name
            extension = Path(filename).suffix.lower()

            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail="Both files must be PDF or DOCX documents.",
                )

        async def save_upload(upload: UploadFile) -> Path:
            filename = Path(upload.filename or "").name
            extension = Path(filename).suffix.lower()
            path = UPLOAD_DIR / f"{uuid4().hex}{extension}"
            temporary_paths.append(path)

            total_size = 0

            with path.open("wb") as destination:
                while True:
                    chunk = await upload.read(1024 * 1024)

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{filename} exceeds the 10 MB limit.",
                        )

                    destination.write(chunk)

            if total_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"{filename} is empty.",
                )

            return path

        contract_path = await save_upload(contract_file)
        policy_path = await save_upload(policy_file)

        # Parse contract and reference policy.
        contract = extract_text(str(contract_path))
        policy_document = extract_text(str(policy_path))

        # Extract policy evidence and source locations.
        policy_evidence_result = parse_policy_document(
            str(policy_path)
        )

        # Infer draft rules from the uploaded policy.
        policy_result = extract_policy_rules(
            policy_document["full_text"]
        )
        clauses = extract_clauses(contract["sections"])
        risk_findings = analyze_clause_risks(clauses)

        retrieval_queries = {
            category: (
                f"{category.replace('_', ' ')}. "
                f"{rule.get('description', '')} "
                + " ".join(
                    clause.get("clause_text", "")
                    for clause in clauses
                    if clause.get("category") == category
                )
            ).strip()
            for category, rule in policy_result["rules"].items()
        }
        retrieved_policy_evidence = retrieve_policy_evidence(
            policy_evidence_result["candidate_requirements"],
            retrieval_queries,
        )

        policy_checks = compare_with_policy(
            clauses,
            policy=policy_result["rules"],
            policy_evidence=retrieved_policy_evidence,
        )
        review = run_decision_reviewer_agent(
            clauses=clauses,
            risk_findings=risk_findings,
            policy_checks=policy_checks,
            policy_evidence=retrieved_policy_evidence,
        )

        # Generate a unique review-session ID.
        analysis_id = str(uuid4())

        # Assign a stable ID to every reviewer item.
        review_items = review.get("items", [])

        for index, item in enumerate(review_items):
            item["item_id"] = (
                f"{item.get('item_type', 'review_item')}:{index}"
            )

        review["llm_review"] = run_optional_llm_evidence_review(
            clauses=clauses,
            risk_findings=risk_findings,
            policy_checks=policy_checks,
            policy_evidence=retrieved_policy_evidence,
            reviewer_items=review_items,
        )

        # Build the complete analysis response before saving.
        analysis_result = {
            "message": "Contract and policy comparison completed.",
            "analysis_id": analysis_id,
            "contract_filename": contract_filename,
            "policy_filename": policy_filename,
            "contract_clause_count": len(clauses),
            "risk_finding_count": len(risk_findings),
            "policy_check_count": len(policy_checks),
            "review_status": determine_review_status(
                policy_checks,
                risk_findings,
            ),
            "clauses": clauses,
            "risk_findings": risk_findings,
            "policy_checks": policy_checks,
            "reviewer_result": review,
            "policy_rules_review_status": policy_result[
                "review_status"
            ],
            "policy_retrieval": {
                "method": "sentence-transformers + FAISS",
                "passage_count": len(retrieved_policy_evidence),
                "top_k_per_requirement": 3,
            },
            "notice": (
                "This is a preliminary comparison using deterministic "
                "rules and, when configured, an LLM evidence-review "
                "step. "
                "Policy rules inferred from document text are drafts "
                "and require human confirmation. Evidence checks "
                "do not establish that a finding is legally correct. "
                "This system does not provide legal advice."
            ),
        }

        # Persist reviewer items and the complete analysis.
        try:
            create_review_session(
                analysis_id=analysis_id,
                contract_filename=contract_filename,
                policy_filename=policy_filename,
                items=review_items,
                analysis_result=analysis_result,
            )
        except (SQLAlchemyError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Analysis completed, but the review could not "
                    "be saved. Check the database configuration "
                    "and connection."
                ),
            ) from exc

        return analysis_result

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not process a document: {exc}",
        ) from exc

    finally:
        for upload in uploads:
            await upload.close()

        for path in temporary_paths:
            if path.exists():
                path.unlink()


@app.post("/api/v1/documents/compare-versions")
async def compare_contract_versions(
    old_contract_file: UploadFile = File(...),
    new_contract_file: UploadFile = File(...),
):
    uploads = [old_contract_file, new_contract_file]
    temporary_paths = []

    try:
        for upload in uploads:
            filename = Path(upload.filename or "").name
            extension = Path(filename).suffix.lower()

            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail="Both versions must be PDF or DOCX documents.",
                )

        async def save_version(upload: UploadFile) -> Path:
            filename = Path(upload.filename or "").name
            extension = Path(filename).suffix.lower()
            path = UPLOAD_DIR / f"{uuid4().hex}{extension}"
            temporary_paths.append(path)
            total_size = 0

            with path.open("wb") as destination:
                while True:
                    chunk = await upload.read(1024 * 1024)

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{filename} exceeds the 10 MB limit.",
                        )

                    destination.write(chunk)

            if total_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"{filename} is empty.",
                )

            return path

        old_path = await save_version(old_contract_file)
        new_path = await save_version(new_contract_file)
        old_document = extract_text(str(old_path))
        new_document = extract_text(str(new_path))
        comparison = run_contract_comparison_agent(
            old_document["full_text"],
            new_document["full_text"],
        )

        return {
            **comparison,
            "old_filename": Path(old_contract_file.filename or "").name,
            "new_filename": Path(new_contract_file.filename or "").name,
            "change_basis": "extracted text lines (1-based)",
        }

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not compare contract versions: {exc}",
        ) from exc
    finally:
        for upload in uploads:
            await upload.close()

        for temporary_path in temporary_paths:
            if temporary_path.exists():
                temporary_path.unlink()


# Upload and parse contract documents
@app.post("/api/v1/documents/parse")
async def parse_document(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    temporary_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

    try:
        total_size = 0

        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        try:
            result = extract_text(str(temporary_path))
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Could not read this document. "
                    "Please check that it is a valid PDF or DOCX file."
                ),
            ) from exc

        return {
            "message": "Document text extracted successfully.",
            "filename": original_name,
            "file_type": result["file_type"],
            "section_count": result["section_count"],
            "sections": result["sections"],
            "full_text": result["full_text"],
        }

    finally:
        await file.close()

        if temporary_path.exists():
            temporary_path.unlink()


# Extract contract clauses
@app.post("/api/v1/documents/analyze-clauses")
async def analyze_clauses(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    temporary_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

    try:
        total_size = 0

        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        parsed_document = extract_text(str(temporary_path))
        clauses = extract_clauses(parsed_document["sections"])

        return {
            "message": "Clause analysis completed.",
            "filename": original_name,
            "total_clauses": len(clauses),
            "clauses": clauses,
        }

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not analyze this document.",
        ) from exc
    finally:
        await file.close()

        if temporary_path.exists():
            temporary_path.unlink()


# Identify potential contract risks
@app.post("/api/v1/documents/analyze-risks")
async def analyze_document_risks(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    temporary_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

    try:
        total_size = 0

        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        parsed_document = extract_text(str(temporary_path))
        clauses = extract_clauses(parsed_document["sections"])
        findings = analyze_clause_risks(clauses)

        return {
            "message": "Contract risk analysis completed.",
            "filename": original_name,
            "total_clauses": len(clauses),
            "total_findings": len(findings),
            "findings": findings,
            "notice": (
                "Findings are preliminary rule-based flags. "
                "They require policy comparison and human review."
            ),
        }

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not analyze risks in this document.",
        ) from exc
    finally:
        await file.close()

        if temporary_path.exists():
            temporary_path.unlink()


# Compare contract clauses against the default reference policy
@app.post("/api/v1/documents/compare-policy")
async def compare_document_policy(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    temporary_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

    try:
        total_size = 0

        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        parsed_document = extract_text(str(temporary_path))
        clauses = extract_clauses(parsed_document["sections"])
        comparisons = compare_with_policy(clauses)

        return {
            "message": "Policy comparison completed.",
            "filename": original_name,
            "total_clauses": len(clauses),
            "total_policy_checks": len(comparisons),
            "policy_checks": comparisons,
            "notice": (
                "The default policy is illustrative. "
                "Results are preliminary and require human review."
            ),
        }

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not compare the document with the policy.",
        ) from exc
    finally:
        await file.close()

        if temporary_path.exists():
            temporary_path.unlink()


# Complete contract analysis using LangGraph
@app.post("/api/v1/documents/analyze")
async def analyze_complete_contract(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    temporary_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

    try:
        total_size = 0

        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        parsed_document = extract_text(str(temporary_path))

        workflow_result = run_contract_workflow(
            parsed_document["sections"]
        )

        clauses = workflow_result["clauses"]
        findings = workflow_result["findings"]
        comparisons = workflow_result["policy_checks"]

        validation = workflow_result.get("validation", {})

        if (
            validation.get("status") != "completed"
            or validation.get("checks_passed") is not True
        ):
            raise HTTPException(
                status_code=500,
                detail="Contract analysis validation failed.",
            )

        risk_summary = {
            "high": sum(
                1
                for finding in findings
                if finding.get("severity") == "high"
            ),
            "medium": sum(
                1
                for finding in findings
                if finding.get("severity") == "medium"
            ),
            "low": sum(
                1
                for finding in findings
                if finding.get("severity") == "low"
            ),
        }

        policy_summary = {
            "deviations_detected": sum(
                1
                for item in comparisons
                if item.get("status") == "deviation_detected"
            ),
            "missing_clauses": sum(
                1
                for item in comparisons
                if item.get("status") == "missing_clause"
            ),
            "needs_review": sum(
                1
                for item in comparisons
                if item.get("status") == "needs_review"
            ),
            "no_deviation_detected": sum(
                1
                for item in comparisons
                if item.get("status") == "no_deviation_detected"
            ),
        }

        return {
            "message": "Complete contract analysis finished.",
            "filename": original_name,
            "document": {
                "file_type": parsed_document["file_type"],
                "section_count": parsed_document["section_count"],
            },
            "workflow_validation": validation,
            "summary": {
                "total_clauses": len(clauses),
                "total_risk_findings": len(findings),
                "total_policy_checks": len(comparisons),
                "risk_severity": risk_summary,
                "policy_results": policy_summary,
                "review_status": determine_review_status(
                    comparisons,
                    findings,
                ),
            },
            "clauses": clauses,
            "risk_findings": findings,
            "policy_checks": comparisons,
            "notice": (
                "This report contains preliminary, rule-based findings. "
                "The default policy is illustrative. Results may be "
                "incomplete or incorrect and must be reviewed by an "
                "appropriately qualified person. This is not legal advice."
            ),
        }

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not complete the contract analysis.",
        ) from exc
    finally:
        await file.close()

        if temporary_path.exists():
            temporary_path.unlink()


# Generate a downloadable PDF analysis report
@app.post("/api/v1/documents/analyze-report")
async def analyze_contract_report(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    temporary_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

    try:
        total_size = 0

        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        parsed_document = extract_text(str(temporary_path))
        clauses = extract_clauses(parsed_document["sections"])
        findings = analyze_clause_risks(clauses)
        comparisons = compare_with_policy(clauses)

        risk_summary = {
            "high": sum(
                1 for item in findings
                if item.get("severity") == "high"
            ),
            "medium": sum(
                1 for item in findings
                if item.get("severity") == "medium"
            ),
            "low": sum(
                1 for item in findings
                if item.get("severity") == "low"
            ),
        }

        policy_summary = {
            "deviations_detected": sum(
                1 for item in comparisons
                if item.get("status") == "deviation_detected"
            ),
            "missing_clauses": sum(
                1 for item in comparisons
                if item.get("status") == "missing_clause"
            ),
            "needs_review": sum(
                1 for item in comparisons
                if item.get("status") == "needs_review"
            ),
            "no_deviation_detected": sum(
                1 for item in comparisons
                if item.get("status") == "no_deviation_detected"
            ),
        }

        summary = {
            "total_clauses": len(clauses),
            "total_risk_findings": len(findings),
            "total_policy_checks": len(comparisons),
            "risk_severity": risk_summary,
            "policy_results": policy_summary,
            "review_status": determine_review_status(
                comparisons,
                findings,
            ),
        }

        document = {
            "file_type": parsed_document["file_type"],
            "section_count": parsed_document["section_count"],
        }

        pdf_file = generate_analysis_pdf(
            filename=original_name,
            document=document,
            summary=summary,
            clauses=clauses,
            findings=findings,
            policy_checks=comparisons,
        )

        download_name = (
            f"{Path(original_name).stem}_analysis_report.pdf"
        )

        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{download_name}"'
                )
            },
        )

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not generate the contract analysis report.",
        ) from exc
    finally:
        await file.close()

        if temporary_path.exists():
            temporary_path.unlink()


# Generate a PDF report comparing a contract with an uploaded policy
@app.post("/api/v1/documents/compare-uploaded-policy-report")
async def compare_uploaded_policy_report(
    contract_file: UploadFile = File(...),
    policy_file: UploadFile = File(...),
):
    uploads = [contract_file, policy_file]
    temporary_paths = []

    try:
        # Validate file extensions.
        for upload in uploads:
            filename = Path(upload.filename or "").name
            extension = Path(filename).suffix.lower()

            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail="Both files must be PDF or DOCX documents.",
                )

        async def save_upload(upload: UploadFile) -> Path:
            filename = Path(upload.filename or "").name
            extension = Path(filename).suffix.lower()
            temporary_path = UPLOAD_DIR / (
                f"{uuid4().hex}{extension}"
            )
            temporary_paths.append(temporary_path)

            total_size = 0

            with temporary_path.open("wb") as destination:
                while True:
                    chunk = await upload.read(1024 * 1024)

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{filename} exceeds the 10 MB limit.",
                        )

                    destination.write(chunk)

            if total_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"{filename} is empty.",
                )

            return temporary_path

        contract_path = await save_upload(contract_file)
        policy_path = await save_upload(policy_file)

        contract = extract_text(str(contract_path))
        policy_document = extract_text(str(policy_path))

        policy_evidence_result = parse_policy_document(
            str(policy_path)
        )

        policy_result = extract_policy_rules(
            policy_document["full_text"]
        )

        clauses = extract_clauses(contract["sections"])
        findings = analyze_clause_risks(clauses)
        retrieval_queries = {
            category: (
                f"{category.replace('_', ' ')}. "
                f"{rule.get('description', '')} "
                + " ".join(
                    clause.get("clause_text", "")
                    for clause in clauses
                    if clause.get("category") == category
                )
            ).strip()
            for category, rule in policy_result["rules"].items()
        }
        retrieved_policy_evidence = retrieve_policy_evidence(
            policy_evidence_result["candidate_requirements"],
            retrieval_queries,
        )

        policy_checks = compare_with_policy(
            clauses,
            policy=policy_result["rules"],
            policy_evidence=retrieved_policy_evidence,
        )

        review = run_decision_reviewer_agent(
            clauses=clauses,
            risk_findings=findings,
            policy_checks=policy_checks,
            policy_evidence=retrieved_policy_evidence,
        )
        review_items = review.get("items", [])
        for index, item in enumerate(review_items):
            item["item_id"] = (
                f"{item.get('item_type', 'review_item')}:{index}"
            )

        review["llm_review"] = run_optional_llm_evidence_review(
            clauses=clauses,
            risk_findings=findings,
            policy_checks=policy_checks,
            policy_evidence=retrieved_policy_evidence,
            reviewer_items=review_items,
        )

        risk_summary = {
            "high": sum(
                1 for item in findings
                if item.get("severity") == "high"
            ),
            "medium": sum(
                1 for item in findings
                if item.get("severity") == "medium"
            ),
            "low": sum(
                1 for item in findings
                if item.get("severity") == "low"
            ),
        }

        policy_summary = {
            "deviations_detected": sum(
                1 for item in policy_checks
                if item.get("status") == "deviation_detected"
            ),
            "missing_clauses": sum(
                1 for item in policy_checks
                if item.get("status") in (
                    "missing",
                    "missing_clause",
                )
            ),
            "needs_review": sum(
                1 for item in policy_checks
                if item.get("status") == "needs_review"
            ),
            "no_deviation_detected": sum(
                1 for item in policy_checks
                if item.get("status") == "no_deviation_detected"
            ),
        }

        summary = {
            "total_clauses": len(clauses),
            "total_risk_findings": len(findings),
            "total_policy_checks": len(policy_checks),
            "risk_severity": risk_summary,
            "policy_results": policy_summary,
            "reviewer_result": review,
            "review_status": determine_review_status(
                policy_checks,
                findings,
            ),
        }

        document = {
            "file_type": contract["file_type"],
            "section_count": contract["section_count"],
        }

        pdf_file = generate_analysis_pdf(
            filename=Path(
                contract_file.filename or "contract"
            ).name,
            policy_filename=Path(
                policy_file.filename or "policy"
            ).name,
            document=document,
            summary=summary,
            clauses=clauses,
            findings=findings,
            policy_checks=policy_checks,
        )

        download_name = (
            f"{Path(contract_file.filename or 'contract').stem}"
            "_comparison_report.pdf"
        )

        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{download_name}"'
                )
            },
        )

    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not process a document: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not generate the contract comparison report. "
                "Check the server terminal for details."
            ),
        ) from exc
    finally:
        for upload in uploads:
            await upload.close()

        for temporary_path in temporary_paths:
            if temporary_path.exists():
                temporary_path.unlink()


# List the 20 most recent saved reviews
@app.get("/api/v1/reviews")
def get_recent_reviews():
    try:
        return {
            "reviews": list_review_sessions(limit=20)
        }
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Review history is temporarily unavailable.",
        ) from exc


# Retrieve a saved review and its decisions
@app.get("/api/v1/reviews/{analysis_id}")
def get_saved_review(analysis_id: str):
    try:
        review = get_review_session(analysis_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Saved review is temporarily unavailable.",
        ) from exc

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="Review session not found.",
        )

    return review


# Save or update a human reviewer's decision
@app.put("/api/v1/reviews/{analysis_id}/{item_id}")
def update_review_decision(
    analysis_id: str,
    item_id: str,
    payload: ReviewDecisionRequest,
):
    try:
        saved = save_review_decision(
            analysis_id=analysis_id,
            item_id=item_id,
            decision=payload.decision,
            comment=payload.comment,
        )
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to save the review decision.",
        ) from exc

    if saved is None:
        raise HTTPException(
            status_code=404,
            detail="Review session or review item not found.",
        )

    return {
        "message": "Review decision saved.",
        "decision": saved,
    }
