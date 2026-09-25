import {
  useEffect,
  useMemo,
  useState,
} from "react";

type Contact = {
  name?: string;
  title?: string;
  linkedin_url?: string;
};

type Prospect = {
  company: string;
  website?: string;
  domain?: string;
  country?: string;
  ai_investment?: string;
  pain_signal?: string;
  likely_team?: string;
  sales_friction?: string;
  priority?: string;
  signal?: string;
  contact?: Contact | null;
  email?: string | null;
  email_status?: string;
  draft_subject?: string;
  draft_body?: string;
  outreach_status?: string;
  sent_at?: string;
  send_error?: string | null;
};

type ProspectRun = {
  run_id: string;
  label?: string;
  status?: string;
  started_at?: string;
  completed_at?: string | null;
  found?: number;
  qualified?: number;
  legacy?: boolean;
  error?: string;
  request?: {
    target_count?: number;
    geography?: string;
    industry?: string;
    ai_signal?: string;
    pain_focus?: string;
    department?: string;
  } | null;
};

type ProspectPoolData = {
  run_id?: string | null;
  is_current?: boolean;
  run?: ProspectRun | null;
  runs?: ProspectRun[];
  prospects: Prospect[];
};

// The sender's real signature lives in frontend/.env.local
// (not committed): VITE_OUTREACH_SIGNATURE="Name\nTitle\nsite"
const SIGNATURE =
  import.meta.env.VITE_OUTREACH_SIGNATURE ??
  "Your Name\nYour title, Your company";


export default function ProspectPool() {
  const [data, setData] =
    useState<ProspectPoolData | null>(null);

  const [selected, setSelected] =
    useState<Set<string>>(
      new Set(),
    );

  const [busy, setBusy] =
    useState(false);

  const [historyOpen, setHistoryOpen] =
    useState(false);

  const [message, setMessage] =
    useState<string | null>(null);

  const [subject, setSubject] =
    useState(
      "AI adoption at {{company}}",
    );

  const [body, setBody] =
    useState(
      `Hi {{first_name}},

Just 15 minutes per employee per day lost to AI rework, poor prompting or unclear workflows can cost a 5,000-person company ~CHF 1.8M every month.

Do you want to stop the bleeding?

Let’s talk.

Best,

${SIGNATURE}`,
    );

  const [useAiSignal, setUseAiSignal] =
    useState(true);

  const [
    usePainSignal,
    setUsePainSignal,
  ] = useState(true);

  const [useRole, setUseRole] =
    useState(true);

  const [
    generatingDrafts,
    setGeneratingDrafts,
  ] = useState(false);

  const [sending, setSending] =
    useState(false);

  const load = async (
    runId?: string,
  ) => {
    const suffix = runId
      ? `?run_id=${encodeURIComponent(
          runId,
        )}`
      : "";

    const response = await fetch(
      `/api/prospects${suffix}`,
    );

    if (!response.ok) {
      throw new Error(
        `Prospects returned ${response.status}`,
      );
    }

    const result =
      (await response.json()) as ProspectPoolData;

    setData(result);
  };

  useEffect(() => {
    void load();
  }, []);

  const visible = useMemo(
    () =>
      (data?.prospects ?? []).filter(
        (item) =>
          item.priority !== "REJECT",
      ),
    [data],
  );

  const counts = useMemo(() => {
    const result = {
      HIGH: 0,
      MEDIUM: 0,
      LOW: 0,
    };

    for (const item of visible) {
      const priority =
        item.priority as keyof typeof result;

      if (priority in result) {
        result[priority] += 1;
      }
    }

    return result;
  }, [visible]);

  const toggle = (
    domain: string,
  ) => {
    setSelected((current) => {
      const next = new Set(
        current,
      );

      if (next.has(domain)) {
        next.delete(domain);
      } else {
        next.add(domain);
      }

      return next;
    });
  };

  const selectAll = () => {
    setSelected(
      new Set(
        visible
          .filter(
            (item) => item.domain,
          )
          .map(
            (item) =>
              item.domain as string,
          ),
      ),
    );
  };

  const clearSelection = () => {
    setSelected(
      new Set(),
    );
  };

  const switchRun = async (
    runId: string,
  ) => {
    setSelected(
      new Set(),
    );
    setMessage(null);

    await load(
      runId || undefined,
    );
  };

  const selectHigh = () => {
    setSelected(
      new Set(
        visible
          .filter(
            (item) =>
              item.priority === "HIGH" &&
              item.domain,
          )
          .map(
            (item) =>
              item.domain as string,
          ),
      ),
    );
  };

  const findEmails = async () => {
    if (selected.size === 0) {
      return;
    }

    setBusy(true);
    setMessage(null);

    try {
      const response = await fetch(
        "/api/prospects/enrich",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            domains: Array.from(
              selected,
            ),
          }),
        },
      );

      const result =
        await response.json();

      if (!response.ok) {
        throw new Error(
          result.detail ??
            "Email enrichment failed.",
        );
      }

      setMessage(
        `Found ${result.emails_found} email(s) from ${result.attempted} prospect(s).`,
      );

      await load(
        data?.run_id ?? undefined,
      );

    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Email enrichment failed.",
      );

    } finally {
      setBusy(false);
    }
  };

  const generateDrafts = async () => {
    if (selected.size === 0) {
      return;
    }

    setGeneratingDrafts(true);
    setMessage(null);

    try {
      const response = await fetch(
        "/api/prospects/drafts",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            domains: Array.from(
              selected,
            ),
            subject,
            body,
            use_ai_signal:
              useAiSignal,
            use_pain_signal:
              usePainSignal,
            use_role:
              useRole,
          }),
        },
      );

      const result =
        await response.json();

      if (!response.ok) {
        throw new Error(
          result.detail ??
            "Draft generation failed.",
        );
      }

      setMessage(
        `Generated ${result.generated} draft(s). ${result.skipped_no_email} skipped without email.`,
      );

      await load(
        data?.run_id ?? undefined,
      );

    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Draft generation failed.",
      );

    } finally {
      setGeneratingDrafts(false);
    }
  };


  const selectedDrafts =
    visible.filter(
      (prospect) => {
        const domain =
          prospect.domain ?? "";

        return (
          domain &&
          selected.has(domain) &&
          prospect.email &&
          prospect.draft_subject &&
          prospect.draft_body
        );
      },
    );

  const readyToSend =
    selectedDrafts.filter(
      (prospect) =>
        prospect.outreach_status !==
        "SENT",
    );


  const sendSelected = async () => {
    if (
      readyToSend.length === 0
    ) {
      return;
    }

    const confirmed =
      window.confirm(
        `Send ${readyToSend.length} individual email(s) now from the GrundMind mailbox?`,
      );

    if (!confirmed) {
      return;
    }

    setSending(true);
    setMessage(null);

    try {
      const response = await fetch(
        "/api/prospects/send",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            domains:
              readyToSend.map(
                (prospect) =>
                  prospect.domain,
              ),
          }),
        },
      );

      const result =
        await response.json();

      if (!response.ok) {
        throw new Error(
          result.detail ??
            "Email sending failed.",
        );
      }

      setMessage(
        `Sent ${result.sent} email(s). ` +
        `${result.skipped_already_sent} already sent, ` +
        `${result.skipped_not_ready} not ready, ` +
        `${result.failed} failed.`,
      );

      await load(
        data?.run_id ?? undefined,
      );

    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Email sending failed.",
      );

    } finally {
      setSending(false);
    }
  };


  const deepSearch = async (
    prospect: Prospect,
  ) => {
    setMessage(null);

    const response = await fetch(
      "/api/research",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json",
        },
        body: JSON.stringify({
          company: prospect.company,
          website:
            prospect.website ||
            prospect.domain ||
            null,
        }),
      },
    );

    const result =
      await response.json();

    if (!response.ok) {
      setMessage(
        result.detail ??
          "Deep Search could not start.",
      );
      return;
    }

    setMessage(
      `Deep Search started for ${prospect.company}.`,
    );
  };

  if (!data) {
    return null;
  }

  const runs = data.runs ?? [];
  const activeRunId = runs[0]?.run_id;

  return (
    <>
      {runs.length > 0 && (
        <section className="history-panel">
          <button
            type="button"
            className={`history-header history-toggle${
              historyOpen ? " is-open" : ""
            }`}
            aria-expanded={historyOpen}
            onClick={() =>
              setHistoryOpen(
                (open) => !open,
              )
            }
          >
            <div>
              <div className="section-kicker">
                PROSPECT SEARCH HISTORY
              </div>
              <h2>
                Previous prospect searches
              </h2>
            </div>

            <span>
              {runs.length} saved{" "}
              {runs.length === 1
                ? "run"
                : "runs"}
              <span className="history-arrow">
                {historyOpen ? "▾" : "▸"}
              </span>
            </span>
          </button>

          {historyOpen && (
          <div className="history-list">
            {runs.map((run) => {
              const request =
                run.request ?? {};

              const status =
                (
                  run.status ??
                  "unknown"
                ).toUpperCase();

              const isCurrent =
                run.run_id ===
                activeRunId;

              const isOpen =
                run.run_id ===
                data.run_id;

              const when =
                run.completed_at ??
                run.started_at;

              return (
                <article
                  className="history-row"
                  key={run.run_id}
                >
                  <div className="history-company">
                    <strong>
                      {run.legacy
                        ? "Previous pool"
                        : `${
                            request.geography ??
                            "Search"
                          } · ${
                            request.industry ??
                            "All industries"
                          }`}
                    </strong>

                    <span>
                      {when
                        ? new Date(
                            when,
                          ).toLocaleString()
                        : "Unknown date"}
                    </span>

                    {!run.legacy && (
                      <span>
                        {request.ai_signal ??
                          "Any AI signal"}
                        {" · "}
                        {request.pain_focus ??
                          "Any pain signal"}
                        {" · "}
                        {request.department ??
                          "Any department"}
                      </span>
                    )}

                    <span>
                      {request.target_count !==
                      undefined
                        ? `${request.target_count} requested · `
                        : ""}
                      {run.found ?? 0} found
                      {" · "}
                      {run.qualified ?? 0} qualified
                    </span>

                    {run.error && (
                      <span>
                        Error: {run.error}
                      </span>
                    )}
                  </div>

                  <div
                    className={`history-status history-status-${(
                      run.status ??
                      "unknown"
                    ).toLowerCase()}`}
                  >
                    {isCurrent
                      ? `CURRENT · ${status}`
                      : status}
                  </div>

                  <div className="history-phase">
                    {run.legacy
                      ? "Pre-run-tracking results"
                      : run.label ??
                        run.run_id}
                  </div>

                  <button
                    type="button"
                    disabled={isOpen}
                    onClick={() => {
                      void switchRun(
                        run.run_id,
                      );
                    }}
                  >
                    {isOpen
                      ? "OPENED"
                      : "OPEN"}
                  </button>
                </article>
              );
            })}
          </div>
          )}
        </section>
      )}

      <section className="prospect-pool">
      <div className="prospect-pool-header">
        <div>
          <div className="eyebrow">
            PROSPECT POOL
          </div>

          <h2>
            {visible.length} outreach prospects
          </h2>

          <p>
            AI investment, possible pain,
            target team and contact enrichment.
          </p>
        </div>

        <div className="prospect-summary">
          <span>
            {data.is_current
              ? "CURRENT RUN"
              : "HISTORY"}
          </span>

          <select
            aria-label="Prospect search run"
            value={data.run_id ?? ""}
            onChange={(event) => {
              void switchRun(
                event.target.value,
              );
            }}
          >
            {(data.runs ?? []).map(
              (run) => (
                <option
                  key={run.run_id}
                  value={run.run_id}
                >
                  {run.run_id ===
                  data.runs?.[0]?.run_id
                    ? "CURRENT · "
                    : ""}
                  {run.label ??
                    run.run_id}
                  {run.legacy
                    ? " · LEGACY"
                    : ""}
                </option>
              ),
            )}
          </select>

          <span>
            HIGH {counts.HIGH}
          </span>
          <span>
            MEDIUM {counts.MEDIUM}
          </span>
          <span>
            LOW {counts.LOW}
          </span>
        </div>
      </div>

      <div className="prospect-actions">
        <button
          type="button"
          onClick={selectAll}
        >
          SELECT ALL
        </button>

        <button
          type="button"
          onClick={selectHigh}
        >
          SELECT HIGH
        </button>

        <button
          type="button"
          disabled={
            selected.size === 0
          }
          onClick={
            clearSelection
          }
        >
          CLEAR
        </button>

        <button
          type="button"
          disabled={
            selected.size === 0 ||
            busy
          }
          onClick={() => {
            void findEmails();
          }}
        >
          {busy
            ? "FINDING EMAILS"
            : `FIND EMAILS (${selected.size})`}
        </button>
      </div>

      {message && (
        <div className="prospect-message">
          {message}
        </div>
      )}

      <section className="outreach-composer">
        <div className="outreach-header">
          <div>
            <div className="section-kicker">
              OUTREACH
            </div>

            <h2>
              Outreach Composer
            </h2>

            <p>
              Write the base message.
              Agent 007 will create an
              individual version for each
              selected prospect.
            </p>
          </div>

          <div className="outreach-count">
            <span>SELECTED</span>
            <strong>
              {selected.size}
            </strong>
          </div>
        </div>

        <label className="outreach-field">
          <span>SUBJECT</span>

          <input
            type="text"
            value={subject}
            onChange={(event) => {
              setSubject(
                event.target.value,
              );
            }}
          />
        </label>

        <label className="outreach-field">
          <span>BODY</span>

          <textarea
            value={body}
            rows={11}
            onChange={(event) => {
              setBody(
                event.target.value,
              );
            }}
          />
        </label>

        <div className="outreach-personalise">
          <span>
            PERSONALISE USING
          </span>

          <label>
            <input
              type="checkbox"
              checked={useAiSignal}
              onChange={(event) => {
                setUseAiSignal(
                  event.target.checked,
                );
              }}
            />
            Company AI activity
          </label>

          <label>
            <input
              type="checkbox"
              checked={usePainSignal}
              onChange={(event) => {
                setUsePainSignal(
                  event.target.checked,
                );
              }}
            />
            Pain / opportunity
          </label>

          <label>
            <input
              type="checkbox"
              checked={useRole}
              onChange={(event) => {
                setUseRole(
                  event.target.checked,
                );
              }}
            />
            Recipient role
          </label>
        </div>

        <div className="outreach-actions">
          <button
            type="button"
            disabled={
              selected.size === 0 ||
              generatingDrafts ||
              !subject.trim() ||
              !body.trim()
            }
            onClick={() => {
              void generateDrafts();
            }}
          >
            {generatingDrafts
              ? "GENERATING DRAFTS"
              : `GENERATE DRAFTS (${selected.size})`}
          </button>
        </div>

        <div className="outreach-hint">
          Available placeholders:
          {" {{company}}, {{first_name}}, {{role}} "}
        </div>
      </section>

      {selectedDrafts.length > 0 && (
        <section className="outreach-review">
          <div className="outreach-review-header">
            <div>
              <div className="section-kicker">
                REVIEW DRAFTS
              </div>

              <h2>
                {selectedDrafts.length}
                {" "}
                personalized email
                {selectedDrafts.length === 1
                  ? ""
                  : "s"}
              </h2>

              <p>
                Open each prospect to inspect
                the exact subject and message
                before sending.
              </p>
            </div>

            <button
              type="button"
              disabled={
                readyToSend.length === 0 ||
                sending
              }
              onClick={() => {
                void sendSelected();
              }}
            >
              {sending
                ? "SENDING"
                : `SEND SELECTED (${readyToSend.length})`}
            </button>
          </div>

          <div className="draft-review-list">
            {selectedDrafts.map(
              (prospect) => {
                const contact =
                  prospect.contact;

                const alreadySent =
                  prospect.outreach_status ===
                  "SENT";

                return (
                  <details
                    className="draft-review-card"
                    key={
                      prospect.domain ||
                      prospect.company
                    }
                  >
                    <summary>
                      <div className="draft-review-summary">
                        <div>
                          <strong>
                            {prospect.company}
                          </strong>

                          <span>
                            {contact?.name ||
                              "Unknown contact"}
                            {" · "}
                            {contact?.title ||
                              "No title"}
                          </span>
                        </div>

                        <div className="draft-review-meta">
                          <span>
                            {prospect.email}
                          </span>

                          <strong>
                            {alreadySent
                              ? "SENT"
                              : "READY"}
                          </strong>
                        </div>
                      </div>
                    </summary>

                    <div className="draft-review-content">
                      <div className="draft-review-subject">
                        <span>SUBJECT</span>

                        <strong>
                          {
                            prospect
                              .draft_subject
                          }
                        </strong>
                      </div>

                      <div className="draft-review-body">
                        {
                          prospect
                            .draft_body
                        }
                      </div>

                      {alreadySent &&
                        prospect.sent_at && (
                          <div className="draft-sent-at">
                            Sent{" "}
                            {new Date(
                              prospect.sent_at,
                            ).toLocaleString()}
                          </div>
                        )}
                    </div>
                  </details>
                );
              },
            )}
          </div>
        </section>
      )}

      <div className="prospect-table-wrap">
        <table className="prospect-table">
          <thead>
            <tr>
              <th />
              <th>COMPANY</th>
              <th>PRIORITY</th>
              <th>AI</th>
              <th>PAIN</th>
              <th>TEAM</th>
              <th>FRICTION</th>
              <th>CONTACT</th>
              <th>EMAIL</th>
              <th />
            </tr>
          </thead>

          <tbody>
            {visible.map(
              (prospect) => {
                const domain =
                  prospect.domain ?? "";

                return (
                  <tr
                    key={
                      domain ||
                      prospect.company
                    }
                  >
                    <td>
                      <input
                        type="checkbox"
                        disabled={!domain}
                        checked={
                          domain
                            ? selected.has(
                                domain,
                              )
                            : false
                        }
                        onChange={() => {
                          if (domain) {
                            toggle(domain);
                          }
                        }}
                      />
                    </td>

                    <td>
                      <strong>
                        {prospect.company}
                      </strong>
                      <small>
                        {prospect.domain}
                      </small>
                    </td>

                    <td>
                      {prospect.priority}
                    </td>

                    <td>
                      {prospect.ai_investment}
                    </td>

                    <td>
                      {prospect.pain_signal}
                    </td>

                    <td>
                      {prospect.likely_team}
                    </td>

                    <td>
                      {prospect.sales_friction}
                    </td>

                    <td>
                      {prospect.contact ? (
                        <>
                          <strong>
                            {
                              prospect
                                .contact
                                .name
                            }
                          </strong>
                          <small>
                            {
                              prospect
                                .contact
                                .title
                            }
                          </small>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>

                    <td>
                      {prospect.email ?? (
                        <small>
                          {
                            prospect.email_status ??
                            "NOT ENRICHED"
                          }
                        </small>
                      )}
                    </td>

                    <td>
                      <button
                        type="button"
                        onClick={() => {
                          void deepSearch(
                            prospect,
                          );
                        }}
                      >
                        DEEP SEARCH
                      </button>
                    </td>
                  </tr>
                );
              },
            )}
          </tbody>
        </table>
      </div>

      </section>
    </>
  );
}
