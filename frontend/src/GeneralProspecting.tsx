import {
  useEffect,
  useState,
} from "react";

import ProspectPool from "./ProspectPool";


type DiscoveryStatus = {
  status:
    | "idle"
    | "running"
    | "completed"
    | "failed";

  progress?: number;
  message?: string | null;
  found?: number;
  qualified?: number;
  error?: string | null;
};


type CompanyList = {
  id: string;
  label: string;
  source: string;
  total: number;
  in_pool: number;
  checked: number;
  remaining: number;
};


export default function GeneralProspecting() {
  // "news": search AI news for companies.
  // "company_list": check each company of a
  // known list, one focused search each.
  const [mode, setMode] =
    useState<"news" | "company_list">(
      "news",
    );

  const [companyLists, setCompanyLists] =
    useState<CompanyList[]>([]);

  const [companyList, setCompanyList] =
    useState("");

  const [targetCount, setTargetCount] =
    useState("100");

  const [geography, setGeography] =
    useState("Europe");

  const [industry, setIndustry] =
    useState("All industries");

  const [aiSignal, setAiSignal] =
    useState(
      "Any meaningful AI activity",
    );

  const [painFocus, setPainFocus] =
    useState(
      "Any relevant signal",
    );

  const [department, setDepartment] =
    useState("Any department");

  const [
    excludeVendors,
    setExcludeVendors,
  ] = useState(true);

  const [
    excludeConsultancies,
    setExcludeConsultancies,
  ] = useState(true);

  const [
    excludeMedia,
    setExcludeMedia,
  ] = useState(true);

  const [
    excludeExisting,
    setExcludeExisting,
  ] = useState(true);

  const [status, setStatus] =
    useState<DiscoveryStatus | null>(
      null,
    );

  const [error, setError] =
    useState<string | null>(null);

  const [poolVersion, setPoolVersion] =
    useState(0);


  const startDiscovery = async () => {
    setError(null);

    try {
      const response = await fetch(
        "/api/discovery",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            mode,
            company_list: companyList,
            target_count:
              Number(targetCount),
            geography,
            industry,
            ai_signal: aiSignal,
            pain_focus: painFocus,
            department,
            exclude_ai_vendors:
              excludeVendors,
            exclude_consultancies:
              excludeConsultancies,
            exclude_research_media:
              excludeMedia,
            exclude_existing:
              excludeExisting,
          }),
        },
      );

      const body =
        await response.json();

      if (!response.ok) {
        throw new Error(
          body.detail ??
            `Discovery returned ${response.status}`,
        );
      }

      setStatus(
        body as DiscoveryStatus,
      );

      // The new run is active immediately.
      // Remount the pool so the old batch
      // disappears while discovery runs.
      setPoolVersion(
        (value) => value + 1,
      );

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to start discovery.",
      );
    }
  };


  // Reload after each run: the number of
  // companies left to check changes.
  useEffect(() => {
    fetch("/api/discovery/lists")
      .then((response) =>
        response.ok
          ? response.json()
          : { lists: [] },
      )
      .then((body) => {
        const lists =
          (body.lists ?? []) as CompanyList[];

        setCompanyLists(lists);

        setCompanyList(
          (current) =>
            current || (lists[0]?.id ?? ""),
        );
      })
      .catch(() => {
        // The news mode still works without lists.
      });
  }, [poolVersion]);


  const selectedList =
    companyLists.find(
      (item) => item.id === companyList,
    );


  const changeMode = (
    next: "news" | "company_list",
  ) => {
    setMode(next);

    // One paid search per company: start small.
    setTargetCount(
      next === "company_list" ? "25" : "100",
    );
  };


  useEffect(() => {
    if (status?.status !== "running") {
      return;
    }

    const timer = window.setInterval(
      async () => {
        try {
          const response = await fetch(
            "/api/discovery/status",
          );

          if (!response.ok) {
            return;
          }

          const next =
            (await response.json()) as DiscoveryStatus;

          setStatus(next);

          if (
            next.status === "completed"
          ) {
            setPoolVersion(
              (value) => value + 1,
            );
          }

          if (
            next.status === "failed"
          ) {
            setError(
              next.error ??
                next.message ??
                "Discovery failed.",
            );
          }

        } catch {
          // Temporary polling errors should
          // not break the page.
        }
      },
      2000,
    );

    return () => {
      window.clearInterval(timer);
    };
  }, [status?.status]);


  const running =
    status?.status === "running";


  return (
    <>
      <section className="general-search">
        <div className="general-search-header">
          <div>
            <div className="section-kicker">
              NEW PROSPECT SEARCH
            </div>

            <h1>
              Find new companies
            </h1>

            <p>
              Search broadly for companies
              showing AI investment, adoption
              activity or potential commercial
              pain.
            </p>
          </div>

          <div className="general-search-target">
            <span>TARGET</span>

            <strong>
              {targetCount}
            </strong>
          </div>
        </div>


        <div className="general-search-grid">
          <label>
            <span>SOURCE</span>

            <select
              value={mode}
              disabled={running}
              onChange={(event) =>
                changeMode(
                  event.target.value as
                    | "news"
                    | "company_list",
                )
              }
            >
              <option value="news">
                Search AI news
              </option>
              <option
                value="company_list"
                disabled={
                  companyLists.length === 0
                }
              >
                Check a company list
              </option>
            </select>
          </label>


          {mode === "company_list" && (
            <label>
              <span>COMPANY LIST</span>

              <select
                value={companyList}
                disabled={running}
                onChange={(event) =>
                  setCompanyList(
                    event.target.value,
                  )
                }
              >
                {companyLists.map((item) => (
                  <option
                    key={item.id}
                    value={item.id}
                  >
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}


          <label>
            <span>
              {mode === "company_list"
                ? "COMPANIES TO CHECK"
                : "NUMBER OF COMPANIES"}
            </span>

            <select
              value={targetCount}
              disabled={running}
              onChange={(event) =>
                setTargetCount(
                  event.target.value,
                )
              }
            >
              {mode === "company_list" && (
                <option value="10">
                  10
                </option>
              )}
              <option value="25">
                25
              </option>
              <option value="50">
                50
              </option>
              <option value="100">
                100
              </option>
              {mode === "news" && (
                <option value="150">
                  150
                </option>
              )}
            </select>
          </label>


          {mode === "news" && (
          <>
          <label>
            <span>GEOGRAPHY</span>

            <select
              value={geography}
              disabled={running}
              onChange={(event) =>
                setGeography(
                  event.target.value,
                )
              }
            >
              <option>Europe</option>
              <option>
                Switzerland
              </option>
              <option>DACH</option>
              <option>
                UK & Ireland
              </option>
              <option>France</option>
              <option>Benelux</option>
              <option>Nordics</option>
              <option>
                Southern Europe
              </option>
              <option>Worldwide</option>
            </select>
          </label>


          <label>
            <span>INDUSTRY</span>

            <select
              value={industry}
              disabled={running}
              onChange={(event) =>
                setIndustry(
                  event.target.value,
                )
              }
            >
              <option>
                All industries
              </option>
              <option>
                Manufacturing
              </option>
              <option>
                Consumer / Retail
              </option>
              <option>
                Financial Services
              </option>
              <option>
                Insurance
              </option>
              <option>
                Pharma / Life Sciences
              </option>
              <option>Energy</option>
              <option>Telecom</option>
              <option>
                Transport / Logistics
              </option>
              <option>
                Professional Services
              </option>
              <option>Technology</option>
            </select>
          </label>
          </>
          )}


          <label>
            <span>AI SIGNAL</span>

            <select
              value={aiSignal}
              disabled={running}
              onChange={(event) =>
                setAiSignal(
                  event.target.value,
                )
              }
            >
              <option>
                Any meaningful AI activity
              </option>
              <option>
                GenAI adoption
              </option>
              <option>
                Enterprise AI rollout
              </option>
              <option>
                AI workflow automation
              </option>
              <option>
                AI investment
              </option>
              <option>
                AI governance / enablement
              </option>
              <option>AI hiring</option>
              <option>
                AI transformation
              </option>
            </select>
          </label>


          <label>
            <span>
              PAIN / OPPORTUNITY
            </span>

            <select
              value={painFocus}
              disabled={running}
              onChange={(event) =>
                setPainFocus(
                  event.target.value,
                )
              }
            >
              <option>
                Any relevant signal
              </option>
              <option>
                ROI / value
              </option>
              <option>
                Adoption friction
              </option>
              <option>
                Workflow friction
              </option>
              <option>
                Governance
              </option>
              <option>Scaling</option>
              <option>
                Quality / remediation
              </option>
              <option>
                Workforce / capability
              </option>
            </select>
          </label>


          <label>
            <span>
              LIKELY DEPARTMENT
            </span>

            <select
              value={department}
              disabled={running}
              onChange={(event) =>
                setDepartment(
                  event.target.value,
                )
              }
            >
              <option>
                Any department
              </option>
              <option>Operations</option>
              <option>Finance</option>
              <option>
                Supply Chain
              </option>
              <option>
                Customer Experience
              </option>
              <option>Marketing</option>
              <option>
                HR / People
              </option>
              <option>IT / AI</option>
              <option>
                Digital Transformation
              </option>
              <option>R&D</option>
              <option>Innovation</option>
            </select>
          </label>
        </div>


        {mode === "company_list" &&
          selectedList && (
            <p className="general-list-note">
              {selectedList.remaining} of{" "}
              {selectedList.total} companies
              left to check (
              {selectedList.in_pool} already in
              the pool, {selectedList.checked}{" "}
              checked in the last 6 months).
              One web search per company; only
              companies with a public AI signal
              are kept. Source:{" "}
              {selectedList.source}
            </p>
          )}


        <div className="general-exclusions">
          <div className="general-exclusions-title">
            EXCLUDE FROM DISCOVERY
          </div>

          <label>
            <input
              type="checkbox"
              checked={excludeVendors}
              disabled={running}
              onChange={(event) =>
                setExcludeVendors(
                  event.target.checked,
                )
              }
            />
            AI vendors
          </label>

          <label>
            <input
              type="checkbox"
              checked={
                excludeConsultancies
              }
              disabled={running}
              onChange={(event) =>
                setExcludeConsultancies(
                  event.target.checked,
                )
              }
            />
            Consultancies / IT services
          </label>

          <label>
            <input
              type="checkbox"
              checked={excludeMedia}
              disabled={running}
              onChange={(event) =>
                setExcludeMedia(
                  event.target.checked,
                )
              }
            />
            Research / media
          </label>

          <label>
            <input
              type="checkbox"
              checked={excludeExisting}
              disabled={running}
              onChange={(event) =>
                setExcludeExisting(
                  event.target.checked,
                )
              }
            />
            Existing prospect pool
          </label>
        </div>


        <div className="general-search-action">
          <button
            type="button"
            disabled={running}
            onClick={() => {
              void startDiscovery();
            }}
          >
            {running
              ? "SEARCHING"
              : "FIND PROSPECTS"}
          </button>
        </div>


        {status &&
          status.status === "running" && (
            <div className="general-progress">
              <div>
                <strong>
                  DISCOVERY RUNNING
                </strong>

                <span>
                  {status.message ??
                    "Searching for prospects..."}
                </span>
              </div>

              <div className="research-progress-track">
                <div
                  className="research-progress-fill"
                  style={{
                    width: `${
                      status.progress ?? 0
                    }%`,
                  }}
                />
              </div>
            </div>
          )}


        {status?.status ===
          "completed" && (
          <div className="general-complete">
            <strong>
              DISCOVERY COMPLETE
            </strong>

            <span>
              {status.found ??
                targetCount}{" "}
              discovered
              {status.qualified
                ? ` · ${status.qualified} qualified`
                : ""}
            </span>
          </div>
        )}


        {error && (
          <div className="research-error">
            {error}
          </div>
        )}
      </section>


      <ProspectPool
        key={poolVersion}
      />
    </>
  );
}
