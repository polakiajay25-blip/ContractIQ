# ContractIQ — Agentic AI Contract Review & Risk Identification System

ContractIQ is an AI-powered contract review system that analyzes business contracts, extracts and classifies clauses, compares contractual terms against reference policies, identifies potential risks and deviations, and generates evidence-based reports to support human review.

The project provides a web interface and a FastAPI backend for document ingestion, policy comparison, contract version comparison, risk analysis, and reviewer decisions.

## Project Links

- **Live Application:** https://contract-iq-seven.vercel.app/
- **Backend API:** https://contractiq-api-12cr.onrender.com
- **API Documentation:** https://contractiq-api-12cr.onrender.com/docs
- **API Health Check:** https://contractiq-api-12cr.onrender.com/health
- **GitHub Repository:** https://github.com/polakiajay25-blip/ContractIQ

## Features

### 1. Document Ingestion
- Upload supported PDF and DOCX documents.
- Validate file types and file sizes.
- Extract text from uploaded contracts and policy documents.

### 2. Clause Extraction and Classification
- Extract relevant clauses from contracts.
- Organize clauses into categories such as payment, confidentiality, liability, termination, warranties, intellectual property, indemnity, and dispute resolution.

### 3. Policy Comparison
- Compare contract clauses against reference policies or templates.
- Extract candidate requirements and draft rules from uploaded policy documents.
- Identify potential differences between contract terms and policy requirements.
- Provide comparison findings and supporting evidence.

### 4. Risk Identification
- Flag potential contractual risks.
- Highlight relevant contract wording and source locations.
- Categorize findings to help reviewers prioritize their examination.

### 5. Contract Version Comparison
- Compare different contract versions.
- Identify changes that may require additional review.

### 6. Human Reviewer Mechanism
- Present flagged items for human verification.
- Support reviewer decisions and updates to review items.
- Allow reviewers to examine evidence before accepting or rejecting findings.

### 7. Report Generation
- Generate structured contract analysis reports.
- Include clause information, risk findings, policy comparison results, and review information where available.
- Support PDF report generation through the implemented report endpoint.

### 8. Review History and Authentication
- Provide authenticated access to protected API endpoints.
- Support retrieval of saved review records.
- Persist review information using the configured database.

## Technology Stack

### Frontend
- React
- TypeScript
- Vite

### Backend
- Python
- FastAPI
- Pydantic
- Uvicorn

### Document Processing and Analysis
- PDF and DOCX text extraction
- Clause extraction and classification
- Token-overlap policy retrieval
- Policy rule extraction and comparison
- Risk analysis
- Evidence-based review
- Contract version comparison

### Database and Storage
- SQLAlchemy for database access
- PostgreSQL support through `DATABASE_URL`
- SQLite fallback for local development

### Authentication and API
- JWT-based authentication
- CORS configuration
- Request and document validation

### Testing and Development
- Pytest
- ESLint
- Git
- GitHub
- Visual Studio Code

### Deployment
- Vercel for the frontend
- Render for the backend

## System Architecture

```text
                  User
                   |
                   v
          React + TypeScript
             (Vite Frontend)
                   |
                   v
              FastAPI API
                   |
                   v
          Document Ingestion
                   |
                   v
          Document Text Parsing
                   |
                   v
        Clause Extraction and
            Classification
                   |
                   v
        Policy Rule Extraction
                   |
                   v
          Policy Comparison
                   |
                   v
             Risk Analysis
                   |
                   v
       Evidence-Based Reviewer
             Mechanism
                   |
                   v
       Report Generation and
          Review Persistence
```

## How It Works

1. The user uploads a contract and, when required, a reference policy.
2. The backend validates the documents and extracts their text.
3. Relevant clauses are identified and classified into categories.
4. Policy requirements are extracted or supplied from the reference policy.
5. Contract terms are compared against applicable requirements.
6. Potential risks and deviations are identified with supporting evidence.
7. The reviewer examines the findings and records decisions.
8. A structured report is generated for further review.

## Policy Retrieval Approach

The current lightweight policy retrieval implementation uses **token-overlap matching** to identify policy passages relevant to a requirement.

This approach reduces dependency and memory requirements compared with embedding-based retrieval. However, it may miss relevant passages when the same meaning is expressed using different words.

Retrieved passages and automatically inferred policy rules should be verified by a human reviewer.

## Example Policy Deviation

**Reference policy:** Payment must be completed within 30 days.

**Contract clause:** Payment is due within 45 days.

**Potential finding:** The contract permits a longer payment period than the reference policy.

**Reviewer action:** Verify the source wording, confirm that the policy applies to the contract, and determine the appropriate action.

This example illustrates the intended comparison behavior; actual detection depends on the implemented comparison rules and input documents.

## Project Structure

```text
Contract_Review_System/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── services/
│   │   ├── main.py
│   │   └── ...
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   └── ...
├── .gitignore
└── README.md
```

The exact files and subdirectories may evolve during development.

## Prerequisites

- Python 3.12
- Node.js and npm
- Git

Additional configuration may be required for the deployed database and authentication.

## Local Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/polakiajay25-blip/ContractIQ.git
cd ContractIQ
```

### 2. Set Up the Backend

From the repository root, create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation in the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

Start the backend:

```powershell
uvicorn app.main:app --app-dir backend --reload
```

The backend should be available at:

`http://127.0.0.1:8000`

Interactive API documentation:

`http://127.0.0.1:8000/docs`

### 3. Set Up the Frontend

Open another terminal and run:

```powershell
cd frontend
npm install
```

Configure the frontend API base URL using the environment-variable name expected by the frontend code. For local development, the configured URL should point to:

`http://127.0.0.1:8000`

Start the frontend:

```powershell
npm run dev
```

Vite will display the local development URL, normally:

`http://localhost:5173`

### 4. Build and Lint the Frontend

From the `frontend` directory:

```powershell
npm run build
npm run lint
```

## Running Tests

From the repository root, activate the virtual environment and run:

```powershell
python -m pytest backend\tests -v
```

Run the tests before submitting changes to verify that the current implementation passes its test suite.

## API Overview

The backend includes routes for authentication, document analysis, policy comparison, contract version comparison, report generation, and review management.

Key documented endpoints include:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check backend health |
| POST | `/api/v1/auth/token` | Obtain an authentication token |
| POST | `/api/v1/documents/compare-uploaded-policy` | Compare a contract with an uploaded policy |
| POST | `/api/v1/documents/compare-versions` | Compare contract versions |
| GET | `/api/v1/reviews` | Retrieve review records |
| GET | `/api/v1/reviews/{analysis_id}` | Retrieve a specific review |
| PUT | `/api/v1/reviews/{analysis_id}/{item_id}` | Update a review item |
| POST | `/api/v1/documents/compare-uploaded-policy-report` | Generate a policy-comparison report |

For the complete list of routes and their request formats, refer to the interactive API documentation:

https://contractiq-api-12cr.onrender.com/docs

Protected endpoints require a valid access token as configured by the backend.

## Database Configuration

The application selects its database based on the `DATABASE_URL` environment variable.

- **PostgreSQL:** Used when a PostgreSQL connection URL is configured.
- **SQLite:** Used as the local fallback when `DATABASE_URL` is not set. The default database file is `data/reviews.db`.

The database layer uses SQLAlchemy to manage database connections and review persistence.

The database used by a particular deployment depends on its environment configuration.

## Deployment

### Frontend

The React frontend is deployed on Vercel:

https://contract-iq-seven.vercel.app/

### Backend

The FastAPI backend is deployed on Render:

https://contractiq-api-12cr.onrender.com

### Source Code

The project repository is hosted on GitHub:

https://github.com/polakiajay25-blip/ContractIQ

The frontend must be configured to communicate with the deployed backend, and the backend CORS configuration must allow the frontend origin.

## Limitations

- Automatically extracted clauses and policy rules may require correction.
- Token-overlap retrieval can miss relevant passages with different wording.
- Document extraction quality depends on the source file and parser.
- Identified risks and policy deviations require human verification.
- Numerical deviation detection should be tested against representative policies and contracts before relying on it.
- Database persistence and protected endpoints depend on correct configuration.

## Future Improvements

Potential improvements, where not already implemented, include:

- Better retrieval of semantically equivalent policy wording.
- Expanded numerical deviation tests for payment periods, service availability, and incident-notification deadlines.
- Additional tests for extraction accuracy and evidence locations.
- Improved handling of scanned documents, if required.
- Further security and deployment testing.

These are potential improvements rather than claims of completed functionality.

## Disclaimer

ContractIQ is intended to assist human contract reviewers. It does not replace professional legal advice. Users should validate the original documents, applicable policy requirements, evidence, and final decisions before relying on a review report.

## Author

Developed as an Agentic AI Contract Review & Risk Identification System project to support document ingestion, clause analysis, policy comparison, risk identification, and evidence-based human review.