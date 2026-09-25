import GeneralProspecting from "./GeneralProspecting";
import { useEffect, useState } from "react";
import "./App.css";

type ActivitySignal = {
  name?: string;
  score?: number;
  max_score?: number;
  evidence_status?: string | null;
  reason?: string;
};

type CommercialSignal = {
  score?: number;
  max_score?: number;
  classification?: string;
  reason?: string;
  evidence_status?: string | null;
};

type Classification = {
  status: string;
  reason: string;
  evidence_refs?: string[];
};

type EvidenceItem = {
  signal?: string;
  claim?: string;
  supported_sources?: string[];
  evidence_status?: string | null;
  source_type?: string | null;
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  COMPANY: "Company source",
  PRESS: "Press / third party",
  JOB_POSTING: "Job posting",
  ACADEMIC: "Academic study",
  VENDOR_CONTENT: "Vendor case study",
};

function sourceTypeLabel(
  sourceType?: string | null,
): string {
  if (!sourceType) {
    return "";
  }

  return (
    SOURCE_TYPE_LABELS[sourceType] ??
    sourceType
  );
}

type Dashboard = {
  company: string;

  activity: {
    score: number;
    max_score: number;
    signals: Record<string, ActivitySignal>;
  };

  commercial_opportunity: {
    score: number;
    max_score: number;
    pain_score: number;
    pain_max_score: number;
    proven_pain: boolean;
    signals: Record<string, CommercialSignal>;
    classifications: Record<string, Classification>;
  };

  account_brief: Record<string, unknown>;
  evidence_catalog: Record<string, EvidenceItem>;
};

type ResearchRun = {
  run_id: string;
  query?: string;
  company?: string | null;
  status?: string;
  started_at?: string | null;
  finished_at?: string | null;
  phase?: string | null;
  phase_index?: number;
  phase_count?: number;
  progress?: number;
  error?: string | null;
  identity_issue?: string | null;
  has_artifacts?: boolean;
};

type ResearchStatus = {
  status: "idle" | "running" | "completed" | "failed";
  company?: string | null;
  phase?: string | null;
  phase_index: number;
  phase_count: number;
  progress: number;
  message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

function formatLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sourceDomain(url?: string) {
  if (!url) return "No source";

  try {
    return new URL(url).hostname.replace("www.", "");
  } catch {
    return url;
  }
}

function EvidenceBadge({
  status,
}: {
  status?: string | null;
}) {
  const normalized = status ?? "UNKNOWN";

  return (
    <span
      className={`badge badge-${normalized.toLowerCase()}`}
    >
      {normalized}
    </span>
  );
}

function ResearchHistoryPanel({
  runs,
  onOpen,
}: {
  runs: ResearchRun[];
  onOpen: (runId: string) => void;
}) {
  const visibleRuns = runs.filter(
    (run) => run.status === "completed",
  );

  if (visibleRuns.length === 0) {
    return null;
  }

  return (
    <section className="history-panel">
      <div className="history-header">
        <div>
          <div className="section-kicker">
            RESEARCH HISTORY
          </div>
          <h2>Previous investigations</h2>
        </div>

        <span>
          {visibleRuns.length} saved{" "}
          {visibleRuns.length === 1 ? "run" : "runs"}
        </span>
      </div>

      <div className="history-list">
        {visibleRuns.map((run) => (
          <article
            className="history-row"
            key={run.run_id}
          >
            <div className="history-company">
              <strong>
                {run.company ??
                  run.query ??
                  "Unknown company"}
              </strong>

              {run.query &&
                run.company &&
                run.query !== run.company && (
                  <span>
                    Query: {run.query}
                  </span>
                )}
            </div>

            <div
              className={`history-status history-status-${(
                run.status ?? "unknown"
              ).toLowerCase()}`}
            >
              {(
                run.status ?? "UNKNOWN"
              ).toUpperCase()}
            </div>

            <div className="history-phase">
              {run.status === "failed"
                ? run.phase ?? "Research failed"
                : run.finished_at
                  ? new Date(
                      run.finished_at,
                    ).toLocaleString()
                  : run.phase ?? ""}
            </div>

            {run.status === "completed" ? (
              <button
                type="button"
                onClick={() =>
                  onOpen(run.run_id)
                }
              >
                OPEN
              </button>
            ) : (
              <span />
            )}
          </article>
        ))}
      </div>

    </section>
  );
}



type AppMode =
  | "general"
  | "deep";


function ModeTabs({
  mode,
  onChange,
}: {
  mode: AppMode;
  onChange: (mode: AppMode) => void;
}) {
  return (
    <nav className="mode-tabs">
      <button
        type="button"
        className={
          mode === "general"
            ? "mode-tab active"
            : "mode-tab"
        }
        onClick={() =>
          onChange("general")
        }
      >
        GENERAL
      </button>

      <button
        type="button"
        className={
          mode === "deep"
            ? "mode-tab active"
            : "mode-tab"
        }
        onClick={() =>
          onChange("deep")
        }
      >
        DEEP SEARCH
      </button>
    </nav>
  );
}

function App() {
  const [appMode, setAppMode] =
    useState<AppMode>("general");

  const [data, setData] = useState<Dashboard | null>(
    null,
  );

  const [error, setError] = useState<string | null>(
    null,
  );

  const [dashboardMissing, setDashboardMissing] =
    useState(false);

  const [showAllEvidence, setShowAllEvidence] =
    useState(false);

  const [companyInput, setCompanyInput] =
    useState("");

  const [websiteInput, setWebsiteInput] =
    useState("");

  const [researchStatus, setResearchStatus] =
    useState<ResearchStatus | null>(null);

  const [researchError, setResearchError] =
    useState<string | null>(null);

  const [historyRuns, setHistoryRuns] =
    useState<ResearchRun[]>([]);

  const loadHistory = async () => {
    try {
      const response = await fetch(
        "/api/research/history",
      );

      if (!response.ok) {
        return;
      }

      const result =
        (await response.json()) as ResearchRun[];

      setHistoryRuns(result);
    } catch {
      // History is supplementary. Do not make the
      // main Agent 007 interface fail with it.
    }
  };

  const openHistoryRun = async (
    runId: string,
  ) => {
    try {
      const response = await fetch(
        `/api/research/history/${encodeURIComponent(
          runId,
        )}/dashboard`,
      );

      if (!response.ok) {
        throw new Error(
          `Saved result returned ${response.status}`,
        );
      }

      const result =
        (await response.json()) as Dashboard;

      setData(result);
      setDashboardMissing(false);
      setShowAllEvidence(false);
      setResearchError(null);
    } catch (err) {
      setResearchError(
        err instanceof Error
          ? err.message
          : "Unable to open saved research.",
      );
    }
  };

  const loadDashboard = async () => {
    try {
      const response = await fetch("/api/dashboard");

      if (response.status === 404) {
        setData(null);
        setDashboardMissing(true);
        setError(null);
        return;
      }

      if (!response.ok) {
        throw new Error(
          `Agent 007 API returned ${response.status}`,
        );
      }

      const result =
        (await response.json()) as Dashboard;

      setData(result);
      setDashboardMissing(false);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load Agent 007.",
      );
    }
  };

  useEffect(() => {
    void loadDashboard();
    void loadHistory();
  }, []);

  useEffect(() => {
    if (researchStatus?.status !== "running") {
      return;
    }

    const poll = window.setInterval(
      async () => {
        try {
          const response = await fetch(
            "/api/research/status",
          );

          if (!response.ok) {
            throw new Error(
              `Research status returned ${response.status}`,
            );
          }

          const status =
            (await response.json()) as ResearchStatus;

          setResearchStatus(status);

          if (status.status === "failed") {
            setResearchError(
              status.error ??
                status.message ??
                "Research failed.",
            );
          }
        } catch (err) {
          setResearchError(
            err instanceof Error
              ? err.message
              : "Unable to read research status.",
          );
        }
      },
      2000,
    );

    return () => {
      window.clearInterval(poll);
    };
  }, [researchStatus?.status]);

  useEffect(() => {
    if (researchStatus?.status === "completed") {
      setShowAllEvidence(false);
      void loadDashboard();
      void loadHistory();
    }

    if (researchStatus?.status === "failed") {
      void loadHistory();
    }
  }, [
    researchStatus?.status,
    researchStatus?.finished_at,
  ]);

  const handleResearch = async () => {
    const company = companyInput.trim();

    if (!company) {
      return;
    }

    setResearchError(null);

    try {
      const response = await fetch(
        "/api/research",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            company,
            website:
              websiteInput.trim() || null,
          }),
        },
      );

      const body = await response.json();

      if (!response.ok) {
        throw new Error(
          body.detail ??
            `Research request returned ${response.status}`,
        );
      }

      setResearchStatus(
        body as ResearchStatus,
      );
    } catch (err) {
      setResearchError(
        err instanceof Error
          ? err.message
          : "Unable to start research.",
      );
    }
  };

  if (appMode === "general") {
    return (
      <main className="app-shell">
        <div className="dashboard">
          <header className="topbar">
            <div className="brand">
              <div className="brand-mark">
                007
              </div>

              <div>
                <div className="product-name">
                  AGENT 007
                </div>

                <div className="product-subtitle">
                  GrundMind Prospect Intelligence
                </div>
              </div>
            </div>

            <div className="account-chip">
              <span>MODE</span>
              <strong>PROSPECTING</strong>
            </div>
          </header>

          <ModeTabs
            mode={appMode}
            onChange={setAppMode}
          />

          <GeneralProspecting />
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="app-shell">
        <div className="error-state">
          <div className="brand-mark">007</div>
          <h1>Agent 007 unavailable</h1>
          <p>{error}</p>
        </div>
      </main>
    );
  }

  if (!data && !dashboardMissing) {
    return (
      <main className="app-shell">
        <div className="loading-state">
          <div className="brand-mark">007</div>
          <span>Loading intelligence…</span>
        </div>
      </main>
    );
  }

  if (!data && dashboardMissing) {
    return (
      <main className="app-shell">
        <div className="dashboard">
          <header className="topbar">
            <div className="brand">
              <div className="brand-mark">007</div>

              <div>
                <div className="product-name">
                  AGENT 007
                </div>
                <div className="product-subtitle">
                  GrundMind Prospect Intelligence
                </div>
              </div>
            </div>
          </header>

          <ModeTabs
            mode={appMode}
            onChange={setAppMode}
          />

          <section className="research-console">
            <div className="research-console-copy">
              <div className="section-kicker">
                NEW INVESTIGATION
              </div>

              <h2>Research a company</h2>

              <p>
                No completed research result is active yet.
                Enter a company and Agent 007 will resolve
                its identity before beginning the evidence
                pipeline.
              </p>
            </div>

            <form
              className="research-form"
              onSubmit={(event) => {
                event.preventDefault();
                void handleResearch();
              }}
            >
              <label htmlFor="company-research-empty">
                COMPANY
              </label>

              <div className="research-input-row">
                <input
                  id="company-research-empty"
                  type="text"
                  value={companyInput}
                  onChange={(event) => {
                    setCompanyInput(
                      event.target.value,
                    );
                  }}
                  placeholder="e.g. Altium International"
                  disabled={
                    researchStatus?.status ===
                    "running"
                  }
                  autoComplete="off"
                />

                <input
                  type="text"
                  value={websiteInput}
                  onChange={(event) => {
                    setWebsiteInput(
                      event.target.value,
                    );
                  }}
                  placeholder="Website (optional), e.g. altium.net"
                  disabled={
                    researchStatus?.status ===
                    "running"
                  }
                  autoComplete="off"
                />

                <button
                  type="submit"
                  disabled={
                    !companyInput.trim() ||
                    researchStatus?.status ===
                      "running"
                  }
                >
                  {researchStatus?.status ===
                  "running"
                    ? "RESEARCHING"
                    : "RESEARCH COMPANY"}
                </button>
              </div>
            </form>

            {researchStatus &&
              researchStatus.status !== "idle" && (
                <div className="research-progress">
                  <div className="research-progress-top">
                    <div>
                      <span>
                        {researchStatus.status.toUpperCase()}
                      </span>

                      <strong>
                        {researchStatus.company ??
                          companyInput}
                      </strong>
                    </div>

                    <div className="research-phase">
                      PHASE{" "}
                      {researchStatus.phase_index}/
                      {researchStatus.phase_count}
                    </div>
                  </div>

                  <div className="research-progress-track">
                    <div
                      className="research-progress-fill"
                      style={{
                        width: `${researchStatus.progress}%`,
                      }}
                    />
                  </div>

                  <div className="research-progress-detail">
                    <strong>
                      {researchStatus.phase ??
                        "Preparing research"}
                    </strong>

                    <span>
                      {researchStatus.message}
                    </span>
                  </div>
                </div>
              )}

            {researchError && (
              <div className="research-error">
                {researchError}
              </div>
            )}
          </section>

          <ResearchHistoryPanel
            runs={historyRuns}
            onOpen={(runId) => {
              void openHistoryRun(runId);
            }}
          />
        </div>
      </main>
    );
  }

  // The loading and empty-dashboard branches above
  // already handle null data. This explicit guard also
  // gives TypeScript a definite non-null boundary.
  if (!data) {
    return null;
  }

  const activitySignals = Object.entries(
    data.activity.signals,
  );

  const classifications = Object.entries(
    data.commercial_opportunity.classifications,
  );

  const evidenceItems = Object.entries(
    data.evidence_catalog,
  );

  const organisationalFit =
    data.commercial_opportunity.signals
      .organisational_fit;

  const brief = data.account_brief as {
    why_this_account?: {
      summary?: string;
      evidence_refs?: string[];
    };
    ai_activity?: Array<{
      finding?: string;
      evidence_refs?: string[];
    }>;
    grundmind_fit?: Array<{
      angle?: string;
      rationale?: string;
      evidence_refs?: string[];
    }>;
    sales_angle?: {
      thesis?: string;
      evidence_refs?: string[];
    };
    uncertainties?: string[];
  };

  return (
    <main className="app-shell">
      <div className="dashboard">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark">007</div>

            <div>
              <div className="product-name">
                AGENT 007
              </div>
              <div className="product-subtitle">
                GrundMind Prospect Intelligence
              </div>
            </div>
          </div>

          <div className="account-chip">
            <span>ACCOUNT</span>
            <strong>{data.company}</strong>
          </div>
        </header>

        <ModeTabs
          mode={appMode}
          onChange={setAppMode}
        />

        <section className="research-console">
          <div className="research-console-copy">
            <div className="section-kicker">
              NEW INVESTIGATION
            </div>

            <h2>Research a company</h2>

            <p>
              Enter a company name. Agent 007 will resolve
              the corporate identity before beginning the
              evidence pipeline.
            </p>
          </div>

          <form
            className="research-form"
            onSubmit={(event) => {
              event.preventDefault();
              void handleResearch();
            }}
          >
            <label htmlFor="company-research">
              COMPANY
            </label>

            <div className="research-input-row">
              <input
                id="company-research"
                type="text"
                value={companyInput}
                onChange={(event) => {
                  setCompanyInput(
                    event.target.value,
                  );
                }}
                placeholder="e.g. Altium International"
                disabled={
                  researchStatus?.status ===
                  "running"
                }
                autoComplete="off"
              />

              <input
                type="text"
                value={websiteInput}
                onChange={(event) => {
                  setWebsiteInput(
                    event.target.value,
                  );
                }}
                placeholder="Website (optional), e.g. altium.net"
                disabled={
                  researchStatus?.status ===
                  "running"
                }
                autoComplete="off"
              />

              <button
                type="submit"
                disabled={
                  !companyInput.trim() ||
                  researchStatus?.status ===
                    "running"
                }
              >
                {researchStatus?.status ===
                "running"
                  ? "RESEARCHING"
                  : "RESEARCH COMPANY"}
              </button>
            </div>
          </form>

          {researchStatus &&
            researchStatus.status !== "idle" && (
              <div className="research-progress">
                <div className="research-progress-top">
                  <div>
                    <span>
                      {researchStatus.status.toUpperCase()}
                    </span>

                    <strong>
                      {researchStatus.company ??
                        companyInput}
                    </strong>
                  </div>

                  <div className="research-phase">
                    PHASE{" "}
                    {researchStatus.phase_index}/
                    {researchStatus.phase_count}
                  </div>
                </div>

                <div className="research-progress-track">
                  <div
                    className="research-progress-fill"
                    style={{
                      width: `${researchStatus.progress}%`,
                    }}
                  />
                </div>

                <div className="research-progress-detail">
                  <strong>
                    {researchStatus.phase ??
                      "Preparing research"}
                  </strong>

                  <span>
                    {researchStatus.message}
                  </span>
                </div>
              </div>
            )}

          {researchError && (
            <div className="research-error">
              {researchError}
            </div>
          )}
        </section>

        

          <ResearchHistoryPanel
          runs={historyRuns}
          onOpen={(runId) => {
            void openHistoryRun(runId);
          }}
        />

        <section className="hero-grid">
          <div className="hero-primary">
            <div className="section-kicker">
              ACCOUNT ASSESSMENT
            </div>

            <h1>{data.company}</h1>

            <p className="hero-copy">
              Evidence-led qualification separates AI
              activity from demonstrated commercial pain.
            </p>

            <div className="hero-statuses">
              <div className="hero-status">
                <span>AI ACTIVITY</span>
                <strong>
                  {data.activity.score}
                  <small>
                    /{data.activity.max_score}
                  </small>
                </strong>
              </div>

              <div className="status-separator" />

              <div className="hero-status">
                <span>PROVEN PAIN</span>
                <strong
                  className={
                    data.commercial_opportunity.proven_pain
                      ? "status-positive"
                      : "status-neutral"
                  }
                >
                  {data.commercial_opportunity.proven_pain
                    ? "YES"
                    : "NONE FOUND"}
                </strong>
              </div>
            </div>
          </div>

          <div className="commercial-card">
            <div className="commercial-label">
              COMMERCIAL OPPORTUNITY
            </div>

            <div className="commercial-score">
              {data.commercial_opportunity.score}
              <span>
                /{data.commercial_opportunity.max_score}
              </span>
            </div>

            <div className="commercial-rule" />

            <p>
              {data.commercial_opportunity.proven_pain
                ? "Commercial pain has been established by accepted evidence."
                : "No evidenced commercial pain currently supports a pain-led sales approach."}
            </p>

            <div className="commercial-gate">
              <span>GATE</span>
              <strong>
                {data.commercial_opportunity.proven_pain
                  ? "OPEN"
                  : "REQUIRES EVIDENCED PAIN"}
              </strong>
            </div>
          </div>
        </section>

        <section className="metric-strip">
          {activitySignals.map(([key, signal]) => (
            <article className="metric" key={key}>
              <div className="metric-top">
                <span>{signal.name}</span>
                <EvidenceBadge
                  status={signal.evidence_status}
                />
              </div>

              <div className="metric-score">
                {signal.score}
                <small>/{signal.max_score}</small>
              </div>
            </article>
          ))}
        </section>

        <section className="section-card brief-section">
          <div className="section-header">
            <div>
              <div className="section-kicker">
                ACCOUNT BRIEF
              </div>
              <h2>What the salesperson needs to know</h2>
            </div>

            <div className="brief-validation">
              VALIDATED BRIEF
            </div>
          </div>

          <div className="brief-grid">
            <article className="brief-block brief-why">
              <div className="brief-label">
                WHY THIS ACCOUNT
              </div>

              <p>
                {brief.why_this_account?.summary ??
                  "No account summary available."}
              </p>
            </article>

            <article className="brief-block brief-fit">
              <div className="brief-label">
                WHERE GRUNDMIND MAY FIT
              </div>

              <div className="fit-list">
                {brief.grundmind_fit?.map(
                  (item, index) => (
                    <div
                      className="fit-item"
                      key={index}
                    >
                      <strong>{item.angle}</strong>
                      <p>{item.rationale}</p>
                    </div>
                  ),
                )}
              </div>
            </article>

            <article className="brief-block brief-sales">
              <div className="brief-label">
                OUTREACH POSTURE
              </div>

              {!data.commercial_opportunity.proven_pain && (
                <div className="outreach-gate">
                  NO PAIN-LED OUTREACH RECOMMENDED
                </div>
              )}

              <h3>Potential relevance</h3>

              <p>
                {brief.sales_angle?.thesis ??
                  "No validated relevance thesis available."}
              </p>
            </article>

            <article className="brief-block brief-uncertainties">
              <div className="brief-label">
                WHAT WE DO NOT KNOW
              </div>

              <ul>
                {brief.uncertainties?.map(
                  (item, index) => (
                    <li key={index}>{item}</li>
                  ),
                )}
              </ul>
            </article>
          </div>
        </section>

        <section className="section-card activity-section">
          <div className="section-header">
            <div>
              <div className="section-kicker">
                ACTIVITY SIGNALS
              </div>

              <h2>What is happening with AI</h2>
            </div>
          </div>

          <div className="activity-table">
            {activitySignals.map(([key, signal]) => (
              <div className="activity-row" key={key}>
                <div>
                  <strong>{signal.name}</strong>
                  <EvidenceBadge
                    status={signal.evidence_status}
                  />
                </div>

                <div className="activity-score">
                  {signal.score}/{signal.max_score}
                </div>

                <p>{signal.reason}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="assessment-grid">
          <div className="section-card commercial-analysis">
            <div className="section-header">
              <div>
                <div className="section-kicker">
                  COMMERCIAL INTERPRETATION
                </div>
                <h2>Evidence of opportunity</h2>
              </div>

              <div className="pain-score">
                <span>PAIN SCORE</span>
                <strong>
                  {
                    data.commercial_opportunity
                      .pain_score
                  }
                  /
                  {
                    data.commercial_opportunity
                      .pain_max_score
                  }
                </strong>
              </div>
            </div>

            <div className="classification-list">
              {classifications.map(
                ([key, classification]) => (
                  <article
                    className="classification-row"
                    key={key}
                  >
                    <div className="classification-name">
                      {formatLabel(key)}
                    </div>

                    <div className="classification-result">
                      {classification.status}
                    </div>

                    <p>{classification.reason}</p>
                  </article>
                ),
              )}
            </div>
          </div>

          <aside className="section-card fit-card">
            <div className="section-kicker">
              QUALIFICATION
            </div>

            <h2>Organisational Fit</h2>

            <div className="fit-score">
              {organisationalFit?.score ?? 0}
              <span>
                /{organisationalFit?.max_score ?? 10}
              </span>
            </div>

            <div className="fit-status">
              QUALIFIED
            </div>

            <p>
              {organisationalFit?.reason ??
                "Qualification information unavailable."}
            </p>

            <div className="qualifier-note">
              Organisational Fit is a qualifier, not
              evidence of commercial pain.
            </div>
          </aside>
        </section>

        <section className="section-card evidence-section">
          <div className="section-header">
            <div>
              <div className="section-kicker">
                EVIDENCE
              </div>

              <h2>Canonical evidence catalog</h2>
            </div>

            <div className="evidence-count">
              {evidenceItems.length} ITEMS
            </div>
          </div>

          <div className="evidence-list">
            {evidenceItems
              .slice(
                0,
                showAllEvidence
                  ? evidenceItems.length
                  : 8,
              )
              .map(([ref, evidence]) => (
                <details
                  className="evidence-item"
                  key={ref}
                >
                  <summary className="evidence-row">
                    <div className="evidence-ref">
                      {ref}
                    </div>

                    <EvidenceBadge
                      status={evidence.evidence_status}
                    />

                    <div className="evidence-content">
                      <strong>
                        {evidence.claim}
                      </strong>

                      <span>
                        {sourceDomain(
                          evidence.supported_sources?.[0],
                        )}
                        {evidence.source_type
                          ? ` · ${sourceTypeLabel(
                              evidence.source_type,
                            )}`
                          : ""}
                      </span>
                    </div>

                    <span className="evidence-chevron">
                      +
                    </span>
                  </summary>

                  <div className="evidence-detail">
                    <div className="evidence-detail-field">
                      <span>REFERENCE</span>
                      <strong>{ref}</strong>
                    </div>

                    <div className="evidence-detail-field">
                      <span>EVIDENCE STATUS</span>
                      <strong>
                        {evidence.evidence_status ??
                          "UNKNOWN"}
                      </strong>
                    </div>

                    {evidence.source_type && (
                      <div className="evidence-detail-field">
                        <span>SOURCE TYPE</span>
                        <strong>
                          {sourceTypeLabel(
                            evidence.source_type,
                          )}
                        </strong>
                      </div>
                    )}

                    <div className="evidence-detail-field evidence-sources">
                      <span>SOURCES</span>

                      {evidence.supported_sources?.length ? (
                        evidence.supported_sources.map(
                          (source) => (
                            <a
                              href={source}
                              target="_blank"
                              rel="noreferrer"
                              key={source}
                            >
                              {source}
                            </a>
                          ),
                        )
                      ) : (
                        <strong>No source available</strong>
                      )}
                    </div>
                  </div>
                </details>
              ))}
          </div>

          {evidenceItems.length > 8 && (
            <div className="evidence-footer">
              <span>
                Showing{" "}
                {showAllEvidence
                  ? evidenceItems.length
                  : 8}{" "}
                of {evidenceItems.length} evidence items
              </span>

              <button
                className="evidence-toggle"
                type="button"
                onClick={() =>
                  setShowAllEvidence(
                    (current) => !current,
                  )
                }
              >
                {showAllEvidence
                  ? "Show less"
                  : `Show all ${evidenceItems.length}`}
              </button>
            </div>
          )}
        </section>

        <footer className="footer">
          <span>
            GrundMind · Agent 007
          </span>

          <span>
            Evidence boundaries and scoring controlled
            deterministically
          </span>
        </footer>
      </div>
    </main>
  );
}

export default App;
