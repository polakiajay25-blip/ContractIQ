
import { useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const ACCESS_TOKEN_KEY = 'contract-review-access-token'
const MAX_FILE_SIZE = 10 * 1024 * 1024

type ReviewTab = 'overview' | 'risks' | 'policy' | 'clauses' | 'reviewer'

type ReviewerDecision =
  | 'accepted'
  | 'rejected'
  | 'needs_further_review'

interface AnalysisItem {
  [key: string]: unknown
  item_id?: string
  item_type?: string
  item?: string
  review_status?: string
  evidence_present?: boolean
  llm_review?: LLMReviewAssessment
}

interface LLMReviewAssessment {
  finding_id?: string
  verdict?: string
  rationale?: string
  contract_quote?: string | null
  contract_quote_verified?: boolean
  contract_source_locations?: string[]
  policy_quote?: string | null
  policy_quote_verified?: boolean
  policy_source_locations?: string[]
  notice?: string
}

interface ReviewerResult {
  [key: string]: unknown
  status?: string
  human_review_required?: boolean
  items?: AnalysisItem[]
  llm_review?: {
    status?: string
    provider?: string
    model?: string
    reviewed_count?: number
    not_reviewed_count?: number
    notice?: string
  }
}

interface SavedDecision {
  item_id: string
  decision: ReviewerDecision
  comment?: string | null
}

interface AnalysisResult {
  analysis_id?: string
  message?: string
  contract_filename?: string
  policy_filename?: string
  contract_clause_count?: number
  risk_finding_count?: number
  policy_check_count?: number
  clauses?: AnalysisItem[]
  risk_findings?: AnalysisItem[]
  policy_checks?: AnalysisItem[]
  reviewer_result?: ReviewerResult
  policy_rules_review_status?: string
  review_status?: string
  notice?: string
}

interface VersionChange {
  change_type: 'added' | 'removed' | 'changed'
  old_lines: string[]
  new_lines: string[]
  old_line_start: number | null
  old_line_end: number | null
  new_line_start: number | null
  new_line_end: number | null
}

interface VersionComparisonResult {
  old_filename: string
  new_filename: string
  has_changes: boolean
  change_count: number
  changes: VersionChange[]
  notice: string
}

interface ReviewSession {
  analysis_id: string
  contract_filename?: string
  policy_filename?: string
  created_at?: string
  items?: AnalysisItem[]
  decisions?: SavedDecision[]
}

function formatStatus(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'Not available'
  }

  return String(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function getRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : {}
}

function getText(item: unknown, keys: string[]): string {
  const record = getRecord(item)

  for (const key of keys) {
    const value = record[key]

    if (typeof value === 'string' && value.trim()) {
      return value
    }

    if (typeof value === 'number') {
      return String(value)
    }
  }

  return ''
}

function getSource(item: unknown): string {
  const record = getRecord(item)

  for (const key of [
    'source',
    'source_paragraphs',
    'location',
    'paragraphs',
  ]) {
    const value = record[key]

    if (Array.isArray(value) && value.length > 0) {
      return value.join(', ')
    }

    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }

  return ''
}

function getSeverityClass(value: unknown): string {
  const severity = String(value ?? '').toLowerCase()

  if (severity === 'high' || severity === 'critical') {
    return 'severity-high'
  }

  if (severity === 'medium' || severity === 'moderate') {
    return 'severity-medium'
  }

  if (severity === 'low') {
    return 'severity-low'
  }

  return 'severity-neutral'
}

function getPolicyStatusClass(value: unknown): string {
  const status = String(value ?? '').toLowerCase()

  if (status === 'deviation_detected' || status === 'missing') {
    return 'severity-high'
  }

  if (status === 'needs_review') {
    return 'severity-medium'
  }

  if (status === 'no_deviation') {
    return 'severity-low'
  }

  return 'severity-neutral'
}

function getErrorMessage(data: unknown, fallback: string): string {
  const record = getRecord(data)
  const detail = record.detail
  const message = record.message

  if (typeof detail === 'string') {
    return detail
  }

  if (typeof message === 'string') {
    return message
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => getRecord(item).msg ?? JSON.stringify(item))
      .join(', ')
  }

  return fallback
}

function App() {
  const [accessToken, setAccessToken] = useState<string | null>(
    () => sessionStorage.getItem(ACCESS_TOKEN_KEY),
  )
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [contractFile, setContractFile] = useState<File | null>(null)
  const [policyFile, setPolicyFile] = useState<File | null>(null)
  const [oldVersionFile, setOldVersionFile] = useState<File | null>(null)
  const [newVersionFile, setNewVersionFile] = useState<File | null>(null)
  const [versionComparison, setVersionComparison] =
    useState<VersionComparisonResult | null>(null)
  const [versionCompareLoading, setVersionCompareLoading] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [activeTab, setActiveTab] = useState<ReviewTab>('overview')
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Reviewer decision state
  const [reviewDecisions, setReviewDecisions] = useState<
    Record<string, ReviewerDecision>
  >({})
  const [reviewComments, setReviewComments] = useState<
    Record<string, string>
  >({})
  const [savingDecisionId, setSavingDecisionId] = useState('')

  // Saved review history state
  const [reviewHistory, setReviewHistory] = useState<ReviewSession[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [openingReviewId, setOpeningReviewId] = useState('')

  async function authorizedFetch(
    input: RequestInfo | URL,
    init: RequestInit = {},
  ): Promise<Response> {
    const headers = new Headers(init.headers)

    if (accessToken) {
      headers.set('Authorization', `Bearer ${accessToken}`)
    }

    const response = await fetch(input, { ...init, headers })

    if (response.status === 401) {
      sessionStorage.removeItem(ACCESS_TOKEN_KEY)
      setAccessToken(null)
      setError('Your session expired. Sign in again to continue.')
      setLoginError('Your session expired. Sign in again to continue.')
    }

    return response
  }

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoginError('')
    setLoginLoading(true)

    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = getRecord(await response.json().catch(() => ({})))

      if (!response.ok) {
        throw new Error(getErrorMessage(data, 'Unable to sign in.'))
      }

      if (typeof data.access_token !== 'string') {
        throw new Error('The server did not return an access token.')
      }

      sessionStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
      setAccessToken(data.access_token)
      setPassword('')
    } catch (err) {
      setLoginError(
        err instanceof Error
          ? err.message
          : 'Unable to connect to the authentication service.',
      )
    } finally {
      setLoginLoading(false)
    }
  }

  function signOut() {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
    setAccessToken(null)
    setResult(null)
    setReviewHistory([])
  }

  function validateFile(file: File): string | null {
    const extension = file.name.split('.').pop()?.toLowerCase()

    if (!['pdf', 'docx'].includes(extension ?? '')) {
      return 'Please upload a PDF or DOCX file.'
    }

    if (file.size === 0) {
      return 'The selected file is empty. Please choose another file.'
    }

    if (file.size > MAX_FILE_SIZE) {
      return 'The file exceeds the 10 MB limit.'
    }

    return null
  }

  function handleFileChange(
    event: React.ChangeEvent<HTMLInputElement>,
    fileType: 'contract' | 'policy',
  ) {
    const file = event.target.files?.[0]

    setError('')
    setSuccess('')

    if (!file) {
      return
    }

    const validationError = validateFile(file)

    if (validationError) {
      setError(validationError)
      event.target.value = ''

      if (fileType === 'contract') {
        setContractFile(null)
      } else {
        setPolicyFile(null)
      }

      return
    }

    if (fileType === 'contract') {
      setContractFile(file)
    } else {
      setPolicyFile(file)
    }

    setResult(null)
    setReviewDecisions({})
    setReviewComments({})
  }

  function handleVersionFileChange(
    event: React.ChangeEvent<HTMLInputElement>,
    version: 'old' | 'new',
  ) {
    const file = event.target.files?.[0]

    setError('')
    setSuccess('')

    if (!file) {
      return
    }

    const validationError = validateFile(file)

    if (validationError) {
      setError(validationError)
      event.target.value = ''
      if (version === 'old') {
        setOldVersionFile(null)
      } else {
        setNewVersionFile(null)
      }
      return
    }

    if (version === 'old') {
      setOldVersionFile(file)
    } else {
      setNewVersionFile(file)
    }
    setVersionComparison(null)
  }

  function createFormData(): FormData {
    const formData = new FormData()

    if (contractFile) {
      formData.append('contract_file', contractFile)
    }

    if (policyFile) {
      formData.append('policy_file', policyFile)
    }

    return formData
  }

  function initializeReviewerState(analysis: AnalysisResult) {
    const initialDecisions: Record<string, ReviewerDecision> = {}
    const initialComments: Record<string, string> = {}

    const reviewerItems = Array.isArray(analysis.reviewer_result?.items)
      ? analysis.reviewer_result.items
      : []

    for (const item of reviewerItems) {
      if (item.item_id) {
        initialDecisions[item.item_id] = 'needs_further_review'
        initialComments[item.item_id] = ''
      }
    }

    setReviewDecisions(initialDecisions)
    setReviewComments(initialComments)
  }

  async function compareDocuments() {
    setError('')
    setSuccess('')

    if (!contractFile || !policyFile) {
      setError('Please upload both a contract and a policy document.')
      return
    }

    setLoading(true)
    setResult(null)
    setReviewDecisions({})
    setReviewComments({})

    try {
      const response = await authorizedFetch(
        `${API_BASE}/api/v1/documents/compare-uploaded-policy`,
        {
          method: 'POST',
          body: createFormData(),
        },
      )

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, 'Unable to compare the documents.'),
        )
      }

      const analysis = data as AnalysisResult

      setResult(analysis)
      initializeReviewerState(analysis)
      setActiveTab('overview')
      setSuccess('Document comparison completed successfully.')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not connect to the backend. Make sure FastAPI is running.',
      )
    } finally {
      setLoading(false)
    }
  }

  async function compareContractVersions() {
    setError('')
    setSuccess('')

    if (!oldVersionFile || !newVersionFile) {
      setError('Please upload both the previous and current contract versions.')
      return
    }

    const formData = new FormData()
    formData.append('old_contract_file', oldVersionFile)
    formData.append('new_contract_file', newVersionFile)
    setVersionCompareLoading(true)
    setVersionComparison(null)

    try {
      const response = await authorizedFetch(
        `${API_BASE}/api/v1/documents/compare-versions`,
        { method: 'POST', body: formData },
      )
      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, 'Unable to compare contract versions.'),
        )
      }

      setVersionComparison(data as VersionComparisonResult)
      setSuccess('Version comparison completed.')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to compare contract versions.',
      )
    } finally {
      setVersionCompareLoading(false)
    }
  }

  async function saveReviewerDecision(item: AnalysisItem) {
    const analysisId = result?.analysis_id
    const itemId = item?.item_id

    if (!analysisId || !itemId) {
      setError(
        'The review or item ID is missing. Please run the analysis again.',
      )
      return
    }

    const decision =
      reviewDecisions[itemId] || 'needs_further_review'
    const comment = reviewComments[itemId] || ''

    setError('')
    setSuccess('')
    setSavingDecisionId(itemId)

    try {
      const response = await authorizedFetch(
        `${API_BASE}/api/v1/reviews/${encodeURIComponent(analysisId)}/${encodeURIComponent(itemId)}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            decision,
            comment,
          }),
        },
      )

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, 'Unable to save the reviewer decision.'),
        )
      }

      // Update the displayed reviewer status after the API confirms the save.
      setResult((previous) => {
        if (!previous) {
          return previous
        }

        const previousReviewer = previous.reviewer_result || {}
        const previousItems = Array.isArray(previousReviewer.items)
          ? previousReviewer.items
          : []

        return {
          ...previous,
          reviewer_result: {
            ...previousReviewer,
            items: previousItems.map((reviewItem) =>
              reviewItem.item_id === itemId
                ? {
                    ...reviewItem,
                    review_status: decision,
                  }
                : reviewItem,
            ),
          },
        }
      })

      setSuccess('Reviewer decision saved successfully.')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to save the reviewer decision.',
      )
    } finally {
      setSavingDecisionId('')
    }
  }

  async function loadReviewHistory() {
    setError('')
    setSuccess('')
    setHistoryLoading(true)

    try {
      const response = await authorizedFetch(`${API_BASE}/api/v1/reviews`)
      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, 'Unable to load review history.'),
        )
      }

      const sessions: ReviewSession[] = Array.isArray(data)
        ? data
        : Array.isArray(data.reviews)
          ? data.reviews
          : Array.isArray(data.items)
            ? data.items
            : []

      setReviewHistory(sessions)

      if (sessions.length === 0) {
        setSuccess('No saved reviews were found.')
      } else {
        setSuccess(`Loaded ${sessions.length} saved review(s).`)
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to load review history. Check that the backend is running.',
      )
    } finally {
      setHistoryLoading(false)
    }
  }

  async function reopenSavedReview(analysisId: string) {
    if (!analysisId) {
      setError('The selected review does not have a valid ID.')
      return
    }

    setError('')
    setSuccess('')
    setOpeningReviewId(analysisId)

    try {
      const response = await authorizedFetch(
        `${API_BASE}/api/v1/reviews/${encodeURIComponent(analysisId)}`,
      )

      const data = (await response.json().catch(() => ({}))) as AnalysisResult & {
        items?: AnalysisItem[]
        decisions?: SavedDecision[]
        created_at?: string
      }

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, 'Unable to reopen this saved review.'),
        )
      }

      const items = Array.isArray(data.items)
        ? data.items as AnalysisItem[]
        : []
      const savedDecisions = Array.isArray(data.decisions)
        ? data.decisions as SavedDecision[]
        : []

      const decisions: Record<string, ReviewerDecision> = {}
      const comments: Record<string, string> = {}

      for (const item of items) {
        if (item.item_id) {
          decisions[item.item_id] = 'needs_further_review'
          comments[item.item_id] = ''
        }
      }

      for (const saved of savedDecisions) {
        if (saved.item_id) {
          const allowedDecisions: ReviewerDecision[] = [
            'accepted',
            'rejected',
            'needs_further_review',
          ]

          if (allowedDecisions.includes(saved.decision)) {
            decisions[saved.item_id] = saved.decision
          }

          comments[saved.item_id] = saved.comment || ''
        }
      }

      const reviewerResult: ReviewerResult = data.reviewer_result || {
        status: 'review_required',
        human_review_required: true,
        items,
      }

      const restoredReviewerItems = (
        Array.isArray(reviewerResult.items)
          ? reviewerResult.items
          : items
      ).map((item) => {
        const saved = savedDecisions.find(
          (entry) => entry.item_id === item.item_id,
        )

        return {
          ...item,
          review_status:
            saved?.decision || item.review_status || 'pending',
        }
      })

      setReviewDecisions(decisions)
      setReviewComments(comments)

      // Restore the complete analysis returned by the backend.
      setResult({
        ...data,
        analysis_id: data.analysis_id || analysisId,
        contract_filename: data.contract_filename,
        policy_filename: data.policy_filename,
        contract_clause_count:
          data.contract_clause_count ??
          (Array.isArray(data.clauses) ? data.clauses.length : 0),
        risk_finding_count:
          data.risk_finding_count ??
          (Array.isArray(data.risk_findings)
            ? data.risk_findings.length
            : 0),
        policy_check_count:
          data.policy_check_count ??
          (Array.isArray(data.policy_checks)
            ? data.policy_checks.length
            : 0),
        clauses: Array.isArray(data.clauses) ? data.clauses : [],
        risk_findings: Array.isArray(data.risk_findings)
          ? data.risk_findings
          : [],
        policy_checks: Array.isArray(data.policy_checks)
          ? data.policy_checks
          : [],
        reviewer_result: {
          ...reviewerResult,
          items: restoredReviewerItems,
        },
      })

      setActiveTab('overview')
      setSuccess('Saved review and analysis results loaded successfully.')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to reopen this saved review.',
      )
    } finally {
      setOpeningReviewId('')
    }
  }

  async function downloadReport() {
    setError('')
    setSuccess('')

    if (!contractFile || !policyFile) {
      setError('Upload both documents before downloading a report.')
      return
    }

    setDownloading(true)

    try {
      const response = await authorizedFetch(
        `${API_BASE}/api/v1/documents/compare-uploaded-policy-report`,
        {
          method: 'POST',
          body: createFormData(),
        },
      )

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))

        throw new Error(
          getErrorMessage(data, 'Unable to generate the PDF report.'),
        )
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')

      link.href = url
      link.download = `${
        contractFile.name.replace(/\.[^.]+$/, '')
      }_comparison_report.pdf`

      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)

      setSuccess('Your PDF report has been downloaded.')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to download the report.',
      )
    } finally {
      setDownloading(false)
    }
  }

  function resetReview() {
    setContractFile(null)
    setPolicyFile(null)
    setResult(null)
    setActiveTab('overview')
    setReviewDecisions({})
    setReviewComments({})
    setVersionComparison(null)
    setError('')
    setSuccess('')

    const inputs = document.querySelectorAll<HTMLInputElement>(
      'input[type="file"]',
    )

    inputs.forEach((input) => {
      input.value = ''
    })
  }

  const clauses = Array.isArray(result?.clauses) ? result.clauses : []
  const risks = Array.isArray(result?.risk_findings)
    ? result.risk_findings
    : []
  const policyChecks = Array.isArray(result?.policy_checks)
    ? result.policy_checks
    : []
  const reviewer = result?.reviewer_result

  const highRisks = risks.filter(
    (item) => String(item?.severity ?? '').toLowerCase() === 'high',
  ).length

  const mediumRisks = risks.filter(
    (item) => String(item?.severity ?? '').toLowerCase() === 'medium',
  ).length

  const lowRisks = risks.filter(
    (item) => String(item?.severity ?? '').toLowerCase() === 'low',
  ).length

  const deviations = policyChecks.filter(
    (item) =>
      String(item?.status ?? '').toLowerCase() === 'deviation_detected',
  ).length

  const needsReview = policyChecks.filter(
    (item) => String(item?.status ?? '').toLowerCase() === 'needs_review',
  ).length

  const tabs: { id: ReviewTab; label: string; count?: number }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'risks', label: 'Risk Findings', count: risks.length },
    { id: 'policy', label: 'Policy Checks', count: policyChecks.length },
    { id: 'clauses', label: 'Contract Clauses', count: clauses.length },
    {
      id: 'reviewer',
      label: 'Reviewer',
      count: Array.isArray(reviewer?.items) ? reviewer.items.length : 0,
    },
  ]

  if (!accessToken) {
    return (
      <main className="app-container auth-shell">
        <section className="auth-card">
          <div className="brand-mark">C</div>
          <p className="eyebrow">SECURE REVIEW WORKSPACE</p>
          <h1>Sign in to ContractIQ</h1>
          <p>
            Use the reviewer credentials configured by your administrator.
          </p>
          <form onSubmit={signIn}>
            <label>
              Username
              <input
                autoComplete="username"
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label>
              Password
              <input
                autoComplete="current-password"
                required
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {loginError && (
              <div className="message message-error" role="alert">
                {loginError}
              </div>
            )}
            <button
              type="submit"
              className="primary-button"
              disabled={loginLoading}
            >
              {loginLoading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </section>
      </main>
    )
  }

  return (
    <main className="app-container">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">C</div>
          <div>
            <h1>ContractIQ</h1>
            <p>AI-Powered Contract Intelligence</p>
          </div>
        </div>

        <div className="header-actions">
          <div className="header-status">
            <span className="status-dot" />
            Contract Review Workspace
          </div>
          <button type="button" className="secondary-button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      <section className="hero-section">
        <div>
          <p className="eyebrow">CONTRACT INTELLIGENCE PLATFORM</p>
          <h2>Review contracts with greater clarity.</h2>
          <p className="hero-description">
            Compare a contract against your policy, identify potential risks,
            inspect supporting evidence, and generate a review report.
          </p>
        </div>
      </section>

      <section className="upload-section">
        <div className="section-heading">
          <div>
            <h2>Start a contract review</h2>
            <p>
              Upload your contract and the policy you want to compare it with.
            </p>
          </div>

          {(contractFile || policyFile || result) && (
            <button
              type="button"
              className="secondary-button"
              onClick={resetReview}
            >
              Start new review
            </button>
          )}
        </div>

        <div className="upload-grid">
          <label className="upload-card">
            <span className="upload-icon">01</span>
            <span className="upload-title">Contract document</span>
            <span className="upload-description">
              Upload the agreement you want to analyze.
            </span>

            <span className="file-picker">
              {contractFile ? 'Change contract' : 'Choose contract'}
            </span>

            <input
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => handleFileChange(event, 'contract')}
            />

            <span className="selected-file">
              {contractFile
                ? contractFile.name
                : 'PDF or DOCX · Maximum 10 MB'}
            </span>
          </label>

          <label className="upload-card">
            <span className="upload-icon">02</span>
            <span className="upload-title">Policy document</span>
            <span className="upload-description">
              Upload the policy containing your expected requirements.
            </span>

            <span className="file-picker">
              {policyFile ? 'Change policy' : 'Choose policy'}
            </span>

            <input
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => handleFileChange(event, 'policy')}
            />

            <span className="selected-file">
              {policyFile
                ? policyFile.name
                : 'PDF or DOCX · Maximum 10 MB'}
            </span>
          </label>
        </div>

        {error && (
          <div className="message message-error" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}

        {success && (
          <div className="message message-success" role="status">
            {success}
          </div>
        )}

        <div className="action-row">
          <button
            type="button"
            className="primary-button"
            onClick={compareDocuments}
            disabled={loading || !contractFile || !policyFile}
          >
            {loading ? 'Analyzing documents...' : 'Analyze contract'}
          </button>

          <p className="action-hint">
            Your documents will be processed by the connected backend.
          </p>
        </div>
      </section>

      <section className="result-card version-compare-card">
        <div className="section-heading">
          <div>
            <h3>Compare contract versions</h3>
            <p>
              Review extracted text changes between two versions. This
              comparison does not determine whether a change is legally
              significant.
            </p>
          </div>
        </div>
        <div className="version-file-grid">
          <label>
            Previous version
            <input
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => handleVersionFileChange(event, 'old')}
            />
            <span className="muted">
              {oldVersionFile?.name || 'PDF or DOCX · Maximum 10 MB'}
            </span>
          </label>
          <label>
            Current version
            <input
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => handleVersionFileChange(event, 'new')}
            />
            <span className="muted">
              {newVersionFile?.name || 'PDF or DOCX · Maximum 10 MB'}
            </span>
          </label>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={compareContractVersions}
          disabled={
            versionCompareLoading || !oldVersionFile || !newVersionFile
          }
        >
          {versionCompareLoading ? 'Comparing versions...' : 'Compare versions'}
        </button>

        {versionComparison && (
          <div className="version-results">
            <h4>
              {versionComparison.change_count} text change
              {versionComparison.change_count === 1 ? '' : 's'} found
            </h4>
            {!versionComparison.has_changes ? (
              <p>No extracted text changes were found.</p>
            ) : (
              <div className="finding-list">
                {versionComparison.changes.map((change, index) => (
                  <article className="finding-item" key={index}>
                    <div className="finding-heading">
                      <h4>{formatStatus(change.change_type)}</h4>
                      <span className="finding-number">
                        Change {String(index + 1).padStart(2, '0')}
                      </span>
                    </div>
                    <p className="muted">
                      Previous version lines:{' '}
                      {change.old_line_start
                        ? `${change.old_line_start}-${change.old_line_end}`
                        : 'No previous text'}
                      {' · '}
                      Current version lines:{' '}
                      {change.new_line_start
                        ? `${change.new_line_start}-${change.new_line_end}`
                        : 'No current text'}
                    </p>
                    {change.old_lines.length > 0 && (
                      <div className="finding-detail">
                        <strong>Previous text</strong>
                        <p>{change.old_lines.join('\n')}</p>
                      </div>
                    )}
                    {change.new_lines.length > 0 && (
                      <div className="finding-detail">
                        <strong>Current text</strong>
                        <p>{change.new_lines.join('\n')}</p>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
            <p className="muted">{versionComparison.notice}</p>
          </div>
        )}
      </section>

      {/* Saved review history */}
      <section className="result-card history-card">
        <div className="history-heading">
          <div>
            <h3>Saved review history</h3>
            <p className="muted">
              Reopen a saved reviewer session and continue reviewing its
              decisions.
            </p>
          </div>

          <button
            type="button"
            className="secondary-button"
            onClick={loadReviewHistory}
            disabled={historyLoading}
          >
            {historyLoading ? 'Loading history...' : 'Load review history'}
          </button>
        </div>

        {reviewHistory.length > 0 ? (
          <div className="history-list">
            {reviewHistory.map((session) => (
              <div className="history-item" key={session.analysis_id}>
                <div>
                  <strong>
                    {session.contract_filename || 'Contract review'}
                  </strong>

                  <p className="muted">
                    Policy: {session.policy_filename || 'Not available'}
                  </p>

                  {session.created_at && (
                    <p className="muted">
                      Saved: {String(session.created_at)}
                    </p>
                  )}
                </div>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => reopenSavedReview(session.analysis_id)}
                  disabled={openingReviewId === session.analysis_id}
                >
                  {openingReviewId === session.analysis_id
                    ? 'Opening...'
                    : 'Open review'}
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">
            Select “Load review history” to retrieve saved sessions.
          </p>
        )}
      </section>

      {loading && (
        <section className="result-card loading-card" aria-live="polite">
          <div className="loading-indicator" />
          <h3>Analyzing your documents</h3>
          <p>
            Extracting clauses, checking policy requirements, and identifying
            potential risks. This may take a little time.
          </p>
        </section>
      )}

      {result && (
        <section className="results-section">
          <div className="results-header">
            <div>
              <p className="eyebrow">ANALYSIS RESULTS</p>
              <h2>Contract review report</h2>
              <p>
                Review the findings and evidence before making decisions.
              </p>
            </div>

            <button
              type="button"
              className="primary-button"
              onClick={downloadReport}
              disabled={downloading}
            >
              {downloading ? 'Generating PDF...' : 'Download PDF report'}
            </button>
          </div>

          <div className="document-summary">
            <div>
              <span>Contract</span>
              <strong>
                {result.contract_filename ||
                  contractFile?.name ||
                  'Contract document'}
              </strong>
            </div>

            <div>
              <span>Policy</span>
              <strong>
                {result.policy_filename ||
                  policyFile?.name ||
                  'Policy document'}
              </strong>
            </div>

            <div>
              <span>Review status</span>
              <strong>
                {formatStatus(
                  result.review_status ||
                    reviewer?.status ||
                    'human_review_required',
                )}
              </strong>
            </div>
          </div>

          <div className="metrics-grid">
            <article className="metric-card">
              <span className="metric-label">Clauses extracted</span>
              <strong>{result.contract_clause_count ?? clauses.length}</strong>
              <span className="metric-caption">
                Contract sections reviewed
              </span>
            </article>

            <article className="metric-card">
              <span className="metric-label">Risk findings</span>
              <strong>{result.risk_finding_count ?? risks.length}</strong>
              <span className="metric-caption">
                Potential issues identified
              </span>
            </article>

            <article className="metric-card">
              <span className="metric-label">Policy checks</span>
              <strong>{result.policy_check_count ?? policyChecks.length}</strong>
              <span className="metric-caption">
                Requirements compared
              </span>
            </article>

            <article className="metric-card">
              <span className="metric-label">Policy deviations</span>
              <strong>{deviations}</strong>
              <span className="metric-caption">
                Items that differ from policy
              </span>
            </article>
          </div>

          <div className="risk-summary">
            <div>
              <span className="severity-tag severity-high">
                {highRisks} High
              </span>
              <span className="severity-tag severity-medium">
                {mediumRisks} Medium
              </span>
              <span className="severity-tag severity-low">
                {lowRisks} Low
              </span>
            </div>

            <p>{needsReview} policy check(s) need additional review.</p>
          </div>

          <nav className="results-tabs" aria-label="Review result sections">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`tab-button ${
                  activeTab === tab.id ? 'active' : ''
                }`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
                {tab.count !== undefined && (
                  <span className="tab-count">{tab.count}</span>
                )}
              </button>
            ))}
          </nav>

          {activeTab === 'overview' && (
            <div className="results-content">
              <section className="result-card">
                <h3>Review overview</h3>
                <p>
                  The comparison has completed. Review the findings below,
                  inspect the source evidence, and confirm important items
                  with an authorized reviewer.
                </p>

                <div className="overview-grid">
                  <div>
                    <span className="overview-number">{risks.length}</span>
                    <span>Risk findings</span>
                  </div>

                  <div>
                    <span className="overview-number">{deviations}</span>
                    <span>Policy deviations</span>
                  </div>

                  <div>
                    <span className="overview-number">{needsReview}</span>
                    <span>Policy checks needing review</span>
                  </div>
                </div>
              </section>

              <section className="result-card">
                <h3>Priority risk findings</h3>

                {risks.length === 0 ? (
                  <p>No risk findings were returned by the analysis.</p>
                ) : (
                  <div className="finding-list">
                    {risks.slice(0, 3).map((item, index) => {
                      const severity =
                        getText(item, ['severity', 'risk_level']) ||
                        'Unclassified'

                      const title =
                        getText(item, [
                          'clause_title',
                          'category',
                          'clause',
                          'title',
                          'name',
                          'risk_type',
                        ]) || `Risk finding ${index + 1}`

                      return (
                        <article className="finding-item" key={index}>
                          <div className="finding-heading">
                            <div>
                              <span className="finding-number">
                                FINDING {String(index + 1).padStart(2, '0')}
                              </span>
                              <h4>{formatStatus(title)}</h4>
                            </div>

                            <span
                              className={`severity-tag ${getSeverityClass(
                                severity,
                              )}`}
                            >
                              {formatStatus(severity)}
                            </span>
                          </div>

                          <p className="finding-description">
                            {getText(item, [
                              'description',
                              'explanation',
                              'reason',
                              'details',
                            ]) ||
                              'Review the finding details and supporting evidence.'}
                          </p>

                          {getText(item, [
                            'recommendation',
                            'suggestion',
                            'recommended_action',
                          ]) && (
                            <div className="finding-detail">
                              <strong>Recommended action</strong>
                              <p>
                                {getText(item, [
                                  'recommendation',
                                  'suggestion',
                                  'recommended_action',
                                ])}
                              </p>
                            </div>
                          )}
                        </article>
                      )
                    })}
                  </div>
                )}

                {risks.length > 3 && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setActiveTab('risks')}
                  >
                    View all {risks.length} findings
                  </button>
                )}
              </section>

              <section className="result-card">
                <h3>Policy comparison summary</h3>

                {policyChecks.length === 0 ? (
                  <p>No policy checks were returned.</p>
                ) : (
                  <div className="finding-list">
                    {policyChecks.slice(0, 4).map((item, index) => {
                      const title =
                        getText(item, [
                          'clause_title',
                          'category',
                          'clause',
                          'rule',
                          'policy_rule',
                          'name',
                        ]) || `Policy check ${index + 1}`

                      const status =
                        getText(item, ['status', 'result']) ||
                        'needs_review'

                      return (
                        <article className="finding-item" key={index}>
                          <div className="finding-heading">
                            <h4>{formatStatus(title)}</h4>
                            <span
                              className={`severity-tag ${getPolicyStatusClass(
                                status,
                              )}`}
                            >
                              {formatStatus(status)}
                            </span>
                          </div>

                          <p className="finding-description">
                            {getText(item, [
                              'explanation',
                              'description',
                              'reason',
                              'details',
                            ]) ||
                              'Review this requirement against the contract.'}
                          </p>
                        </article>
                      )
                    })}
                  </div>
                )}
              </section>

              {result.notice && (
                <section className="notice-card">
                  <strong>Important notice</strong>
                  <p>{result.notice}</p>
                </section>
              )}
            </div>
          )}

          {activeTab === 'risks' && (
            <section className="result-card">
              <h3>Risk findings</h3>
              <p>
                Inspect the potential risks, evidence, and suggested next
                steps.
              </p>

              {risks.length === 0 ? (
                <p>No risk findings are available.</p>
              ) : (
                <div className="finding-list">
                  {risks.map((item, index) => {
                    const title =
                      getText(item, [
                        'clause_title',
                        'category',
                        'clause',
                        'title',
                        'name',
                        'risk_type',
                      ]) || `Risk finding ${index + 1}`

                    const severity = getText(item, [
                      'severity',
                      'risk_level',
                    ])

                    const evidence = getText(item, [
                      'evidence',
                      'matched_text',
                      'evidence_text',
                    ])
                    const description = getText(item, [
                      'description',
                      'explanation',
                      'reason',
                      'details',
                    ])

                    const recommendation = getText(item, [
                      'recommendation',
                      'suggestion',
                      'recommended_action',
                    ])

                    const source = getSource(item)
                    return (
                      <article className="finding-item" key={index}>
                        <div className="finding-heading">
                          <div>
                            <span className="finding-number">
                              FINDING {String(index + 1).padStart(2, '0')}
                            </span>
                            <h4>{formatStatus(title)}</h4>
                          </div>

                          <span
                            className={`severity-tag ${getSeverityClass(
                              severity,
                            )}`}
                          >
                            {formatStatus(severity || 'Unclassified')}
                          </span>
                        </div>

                        <p className="finding-description">
                          {description ||
                            'No description was provided for this finding.'}
                        </p>

                        {evidence && (
                          <div className="finding-detail">
                            <strong>Evidence found</strong>
                            <p>{evidence}</p>
                          </div>
                        )}

                        {recommendation && (
                          <div className="finding-detail">
                            <strong>Recommended action</strong>
                            <p>{recommendation}</p>
                          </div>
                        )}

                        {source && (
                          <p className="finding-source">
                            <strong>Source:</strong> {source}
                          </p>
                        )}

                        <p className="finding-review">
                          Requires human verification before any decision is
                          made.
                        </p>
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
          )}

          {activeTab === 'policy' && (
            <section className="result-card">
              <h3>Policy checks</h3>
              <p>
                Compare each policy requirement with the available contract
                evidence.
              </p>

              {policyChecks.length === 0 ? (
                <p>No policy checks are available.</p>
              ) : (
                <div className="finding-list">
                  {policyChecks.map((item, index) => {
                    const title =
                      getText(item, [
                        'clause_title',
                        'category',
                        'clause',
                        'rule',
                        'policy_rule',
                        'name',
                      ]) || `Policy check ${index + 1}`

                    const status =
                      getText(item, ['status', 'result']) || 'needs_review'

                    const requirement = getText(item, [
                      'requirement',
                      'expected_value',
                      'policy_requirement',
                    ])

                    const explanation = getText(item, [
                      'explanation',
                      'description',
                      'reason',
                      'details',
                    ])

                    const evidence = getText(item, [
                      'evidence',
                      'matched_text',
                      'evidence_text',
                    ])

                    const contractRequirement = getText(item, [
                      'contract_requirement',
                    ])
                    const policyEvidence = getText(item, ['policy_evidence'])
                    const source = getSource(item)
                    const policySource = Array.isArray(
                      item?.policy_source_locations,
                    )
                      ? item.policy_source_locations.join(', ')
                      : getText(item, ['policy_source_locations'])

                    return (
                      <article className="finding-item" key={index}>
                        <div className="finding-heading">
                          <div>
                            <span className="finding-number">
                              POLICY CHECK{' '}
                              {String(index + 1).padStart(2, '0')}
                            </span>
                            <h4>{formatStatus(title)}</h4>
                          </div>

                          <span
                            className={`severity-tag ${getPolicyStatusClass(
                              status,
                            )}`}
                          >
                            {formatStatus(status)}
                          </span>
                        </div>

                        {requirement && (
                          <div className="finding-detail">
                            <strong>Reference requirement</strong>
                            <p>{requirement}</p>
                          </div>
                        )}

                        {explanation && (
                          <p className="finding-description">
                            {explanation}
                          </p>
                        )}

                        {evidence && (
                          <div className="finding-detail">
                            <strong>Supporting contract evidence</strong>
                            <p>{evidence}</p>
                          </div>
                        )}

                        {contractRequirement && (
                          <div className="finding-detail">
                            <strong>Contract requirement</strong>
                            <p>{contractRequirement}</p>
                          </div>
                        )}

                        {policyEvidence && (
                          <div className="finding-detail">
                            <strong>Supporting policy evidence</strong>
                            <p>{policyEvidence}</p>
                          </div>
                        )}

                        {source && (
                          <p className="finding-source">
                            <strong>Contract source:</strong> {source}
                          </p>
                        )}

                        {policySource && (
                          <p className="finding-source">
                            <strong>Policy source:</strong> {policySource}
                          </p>
                        )}
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
          )}

          {activeTab === 'clauses' && (
            <section className="result-card">
              <h3>Extracted contract clauses</h3>
              <p>
                Expand a clause to inspect the extracted text and source
                location.
              </p>

              {clauses.length === 0 ? (
                <p>No clauses were returned by the parser.</p>
              ) : (
                <div className="clause-list">
                  {clauses.map((item, index) => {
                    const title =
                      getText(item, [
                        'title',
                        'clause_title',
                        'name',
                        'category',
                        'clause_type',
                      ]) || `Contract clause ${index + 1}`

                    const category = getText(item, [
                      'category',
                      'type',
                      'clause_type',
                    ])

                    const text = getText(item, [
                      'text',
                      'content',
                      'clause_text',
                      'full_text',
                      'description',
                    ])

                    const source = getSource(item)

                    return (
                      <details className="clause-item" key={index}>
                        <summary>
                          <span className="clause-number">
                            {String(index + 1).padStart(2, '0')}
                          </span>
                          <span>{formatStatus(title)}</span>
                        </summary>

                        <div className="clause-content">
                          {category && (
                            <p>
                              <strong>Category:</strong>{' '}
                              {formatStatus(category)}
                            </p>
                          )}

                          <p className="clause-text">
                            {text ||
                              'No extracted text is available for this clause.'}
                          </p>

                          {source && (
                            <p>
                              <strong>Source:</strong> {source}
                            </p>
                          )}

                          {!text && (
                            <details>
                              <summary>View raw clause data</summary>
                              <pre>{JSON.stringify(item, null, 2)}</pre>
                            </details>
                          )}
                        </div>
                      </details>
                    )
                  })}
                </div>
              )}
            </section>
          )}

          {activeTab === 'reviewer' && (
            <section className="result-card">
              <h3>Decision reviewer</h3>

              {reviewer ? (
                <>
                  <div className="reviewer-summary">
                    <div>
                      <span>Review status</span>
                      <strong>{formatStatus(reviewer.status)}</strong>
                    </div>

                    <div>
                      <span>Human review required</span>
                      <strong>
                        {reviewer.human_review_required === true
                          ? 'Yes'
                          : reviewer.human_review_required === false
                            ? 'No'
                            : 'Check reviewer details'}
                      </strong>
                    </div>

                    <div>
                      <span>LLM evidence review</span>
                      <strong>
                        {reviewer.llm_review?.status
                          ? formatStatus(reviewer.llm_review.status)
                          : 'Not available'}
                      </strong>
                    </div>
                  </div>

                  {reviewer.llm_review && (
                    <p className="finding-description">
                      {reviewer.llm_review.provider
                        ? `${reviewer.llm_review.provider} ${
                            reviewer.llm_review.model || ''
                          } reviewed ${
                            reviewer.llm_review.reviewed_count ?? 0
                          } finding(s). `
                        : ''}
                      {reviewer.llm_review.not_reviewed_count
                        ? `${reviewer.llm_review.not_reviewed_count} finding(s) were not reviewed by the LLM. `
                        : ''}
                      {reviewer.llm_review.notice
                        ? `${reviewer.llm_review.notice} `
                        : ''}
                      An LLM assessment is not legal advice and does not
                      replace the source documents or human review.
                    </p>
                  )}

                  <p className="finding-description">
                    Record a reviewer decision and any supporting comments for
                    each item. Saved decisions are stored in the review
                    database. Automated findings still require human
                    verification.
                  </p>

                  {Array.isArray(reviewer.items) &&
                  reviewer.items.length > 0 ? (
                    <div className="reviewer-list">
                      {reviewer.items.map((item, index) => {
                        const itemId = item.item_id

                        const decision = itemId
                          ? reviewDecisions[itemId] ||
                            'needs_further_review'
                          : 'needs_further_review'

                        return (
                          <div
                            className="reviewer-item"
                            key={itemId || index}
                          >
                            <div className="reviewer-item-details">
                              <strong>
                                {formatStatus(
                                  item.item || `Review item ${index + 1}`,
                                )}
                              </strong>

                              <p className="muted">
                                {formatStatus(item.item_type)}
                              </p>

                              {item.evidence_present === false && (
                                <p className="muted">
                                  Evidence was not confirmed.
                                </p>
                              )}

                              {item.llm_review && (
                                <div className="finding-description">
                                  <strong>
                                    LLM assessment:{' '}
                                    {formatStatus(
                                      item.llm_review.verdict || 'uncertain',
                                    )}
                                  </strong>
                                  {item.llm_review.rationale && (
                                    <p>{item.llm_review.rationale}</p>
                                  )}
                                  {item.llm_review.contract_quote && (
                                    <p>
                                      <strong>Contract quote:</strong>{' '}
                                      "{item.llm_review.contract_quote}"
                                      {item.llm_review
                                        .contract_quote_verified
                                        ? ' (verified against extracted text)'
                                        : ' (not verified)'}
                                      {item.llm_review
                                        .contract_source_locations?.length
                                        ? ` — ${item.llm_review.contract_source_locations.join(
                                            ', ',
                                          )}`
                                        : ''}
                                    </p>
                                  )}
                                  {item.llm_review.policy_quote && (
                                    <p>
                                      <strong>Policy quote:</strong>{' '}
                                      "{item.llm_review.policy_quote}"
                                      {item.llm_review.policy_quote_verified
                                        ? ' (verified against extracted text)'
                                        : ' (not verified)'}
                                      {item.llm_review
                                        .policy_source_locations?.length
                                        ? ` — ${item.llm_review.policy_source_locations.join(
                                            ', ',
                                          )}`
                                        : ''}
                                    </p>
                                  )}
                                </div>
                              )}

                              {itemId ? (
                                <div className="decision-controls">
                                  <label>
                                    Reviewer decision
                                    <select
                                      value={decision}
                                      onChange={(event) =>
                                        setReviewDecisions((previous) => ({
                                          ...previous,
                                          [itemId]:
                                            event.target
                                              .value as ReviewerDecision,
                                        }))
                                      }
                                    >
                                      <option value="accepted">
                                        Accepted
                                      </option>
                                      <option value="rejected">
                                        Rejected
                                      </option>
                                      <option value="needs_further_review">
                                        Needs Further Review
                                      </option>
                                    </select>
                                  </label>

                                  <label>
                                    Reviewer comments
                                    <textarea
                                      rows={3}
                                      maxLength={2000}
                                      placeholder="Add a reason, evidence note, or follow-up action..."
                                      value={reviewComments[itemId] || ''}
                                      onChange={(event) =>
                                        setReviewComments((previous) => ({
                                          ...previous,
                                          [itemId]: event.target.value,
                                        }))
                                      }
                                    />
                                  </label>

                                  <button
                                    type="button"
                                    className="primary-button"
                                    onClick={() =>
                                      saveReviewerDecision(item)
                                    }
                                    disabled={
                                      savingDecisionId === itemId ||
                                      !result.analysis_id
                                    }
                                  >
                                    {savingDecisionId === itemId
                                      ? 'Saving...'
                                      : 'Save decision'}
                                  </button>
                                </div>
                              ) : (
                                <p className="muted">
                                  This item has no ID and cannot be saved.
                                  Run a new analysis to create a review session.
                                </p>
                              )}
                            </div>

                            <span className="severity-tag severity-medium">
                              {formatStatus(decision)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <p>No individual reviewer items were returned.</p>
                  )}
                </>
              ) : (
                <p>The API did not return reviewer details.</p>
              )}
            </section>
          )}

          <section className="notice-card">
            <strong>Human review required</strong>
            <p>
              This system provides preliminary, automated contract analysis.
              Findings may be incomplete or incorrect. Confirm important
              clauses, policy rules, and recommendations with an authorized
              reviewer. Do not treat this output as legal advice.
            </p>
          </section>
        </section>
      )}

      <footer className="app-footer">
        <p>ContractIQ · AI-Powered Contract Review System</p>
        <p>
          Automated analysis supports human review; it does not replace it.
        </p>
      </footer>
    </main>
  )
}

export default App
