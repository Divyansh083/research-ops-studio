"use client";

import { ChangeEvent, useDeferredValue, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { 
  ConfigPayload, 
  DatasetArtifact, 
  DatasetRecord, 
  emptySnapshot, 
  Notice, 
  ResearchSnapshot 
} from "../types/research";
import { toBase64 } from "../lib/utils";
import { Sidebar } from "./research/sidebar";
import { Composer } from "./research/composer";
import { MetricsGrid } from "./research/metrics-grid";
import { ResultsPanel } from "./research/results-panel";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const EXAMPLE_QUERY =
  "Create a school dataset and then write and execute a Python script to analyze attendance and subject scores.";

async function parseJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export function ResearchWorkspace() {
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [datasets, setDatasets] = useState<DatasetRecord[]>([]);
  const [selectedDatasetPath, setSelectedDatasetPath] = useState<string | null>(null);
  const [datasetRequest, setDatasetRequest] = useState("");
  const [lastGeneratedDataset, setLastGeneratedDataset] = useState<DatasetArtifact | null>(null);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [statusText, setStatusText] = useState("Ready");
  const [activeTab, setActiveTab] = useState<"report" | "activity" | "dataset" | "artifacts">("report");
  const [researchState, setResearchState] = useState<ResearchSnapshot>(emptySnapshot);
  const [datasetPreview, setDatasetPreview] = useState<{ columns: string[]; data: any[] } | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isGeneratingDataset, setIsGeneratingDataset] = useState(false);
  const [isUploadingDataset, setIsUploadingDataset] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isResearching, setIsResearching] = useState(false);
  const [logOffset, setLogOffset] = useState(0);
  const [, startTransition] = useTransition();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const deferredReport = useDeferredValue(researchState.final_report);

  const selectedDataset = useMemo(() => {
    const lastGeneratedInRun = researchState.dataset_outputs?.[researchState.dataset_outputs.length - 1]?.path;
    const activePath = 
      lastGeneratedInRun ||
      researchState.selected_dataset_path || 
      selectedDatasetPath || 
      lastGeneratedDataset?.path;
    return datasets.find((dataset) => dataset.path === activePath) ?? null;
  }, [datasets, selectedDatasetPath, lastGeneratedDataset, researchState.selected_dataset_path, researchState.dataset_outputs]);

  useEffect(() => {
    void loadWorkspace();
  }, []);

  useEffect(() => {
    if (activeTab === "dataset") {
      const lastGeneratedInRun = researchState.dataset_outputs?.[researchState.dataset_outputs.length - 1]?.path;
      const pathToPreview = 
        lastGeneratedInRun ||
        researchState.selected_dataset_path || 
        selectedDatasetPath || 
        lastGeneratedDataset?.path;

      if (!pathToPreview) {
        setDatasetPreview(null);
        setPreviewError(null);
        return;
      }
      setIsPreviewLoading(true);
      setPreviewError(null);
      parseJson<{ columns: string[]; data: any[] }>(
        `/api/datasets/preview?path=${encodeURIComponent(pathToPreview)}`
      )
        .then(setDatasetPreview)
        .catch((err) => {
          setDatasetPreview(null);
          setPreviewError(err instanceof Error ? err.message : "Failed to load dataset preview.");
        })
        .finally(() => setIsPreviewLoading(false));
    }
  }, [activeTab, selectedDatasetPath, lastGeneratedDataset, researchState.selected_dataset_path, researchState.dataset_outputs]);

  async function loadWorkspace() {
    setIsBootstrapping(true);
    try {
      const payload = await parseJson<ConfigPayload>("/api/config");
      setConfig(payload);
      setDatasets(payload.datasets);
      setNotice(null);
    } catch (error) {
      setNotice({
        tone: "error",
        message: error instanceof Error ? error.message : "Failed to load the workspace.",
      });
    } finally {
      setIsBootstrapping(false);
    }
  }

  async function refreshDatasets() {
    const payload = await parseJson<{ datasets: DatasetRecord[]; sandbox_ready: boolean }>("/api/datasets");
    setDatasets(payload.datasets);
    setConfig((current) =>
      current
        ? {
            ...current,
            datasets: payload.datasets,
            dataset_count: payload.datasets.length,
            sandbox_ready: payload.sandbox_ready,
          }
        : current,
    );
  }

  async function handleGenerateDataset() {
    if (!datasetRequest.trim()) {
      setNotice({ tone: "error", message: "Describe the dataset you want to create first." });
      return;
    }

    setIsGeneratingDataset(true);
    setNotice(null);
    try {
      const payload = await parseJson<{
        dataset: DatasetArtifact | null;
        selected_dataset_path: string | null;
        datasets: DatasetRecord[];
        error_log: string[];
      }>("/api/datasets/generate", {
        method: "POST",
        body: JSON.stringify({
          request: datasetRequest.trim(),
          selected_dataset_path: selectedDatasetPath,
        }),
      });

      setDatasets(payload.datasets);
      setSelectedDatasetPath(payload.selected_dataset_path ?? null);
      setLastGeneratedDataset(payload.dataset);
      setConfig((current) =>
        current
          ? {
              ...current,
              datasets: payload.datasets,
              dataset_count: payload.datasets.length,
            }
          : current,
      );
      setNotice({
        tone: "success",
        message:
          payload.dataset?.path != null
            ? `Dataset ready: ${payload.dataset.path.split(/[\\/]/).pop()}`
            : "Dataset request completed.",
      });
    } catch (error) {
      setNotice({
        tone: "error",
        message: error instanceof Error ? error.message : "Dataset generation failed.",
      });
    } finally {
      setIsGeneratingDataset(false);
    }
  }

  async function handleClearLogs() {
    setLogOffset(researchState.agent_log.length);
  }

  async function handleUploadDataset(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setIsUploadingDataset(true);
    setNotice(null);
    try {
      const payload = await parseJson<{
        dataset: DatasetRecord;
        selected_dataset_path: string;
        datasets: DatasetRecord[];
      }>("/api/datasets/upload", {
        method: "POST",
        body: JSON.stringify({
          filename: file.name,
          content_base64: await toBase64(file),
        }),
      });

      setDatasets(payload.datasets);
      setSelectedDatasetPath(payload.selected_dataset_path);
      setConfig((current) =>
        current
          ? {
              ...current,
              datasets: payload.datasets,
              dataset_count: payload.datasets.length,
            }
          : current,
      );
      setNotice({
        tone: "success",
        message: `Uploaded dataset: ${payload.dataset.name}`,
      });
    } catch (error) {
      setNotice({
        tone: "error",
        message: error instanceof Error ? error.message : "Dataset upload failed.",
      });
    } finally {
      setIsUploadingDataset(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      event.target.value = "";
    }
  }

  async function handleRunResearch() {
    if (!query.trim()) {
      setNotice({ tone: "error", message: "Write a research brief before running the workflow." });
      return;
    }

    setIsResearching(true);
    setActiveTab("activity");
    setStatusText("Planning the workflow...");
    setNotice(null);
    setLogOffset(0);
    setResearchState({
      ...emptySnapshot,
      query: query.trim(),
      selected_dataset_path: selectedDatasetPath,
      available_datasets: datasets.map((item) => item.path),
    });

    try {
      const response = await fetch(`${API_BASE}/api/research/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: query.trim(),
          selected_dataset_path: selectedDatasetPath,
        }),
      });

      if (!response.ok || !response.body) {
        const text = await response.text();
        throw new Error(text || `Request failed with status ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      
      // Store log timestamps locally to avoid re-render shift
      const logTimestamps: Record<number, string> = {};

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.trim()) {
            continue;
          }

          const event = JSON.parse(line) as {
            type: "start" | "update" | "complete" | "error";
            node?: string;
            message?: string;
            snapshot: ResearchSnapshot;
          };

          // Attach timestamps to new logs
          event.snapshot.agent_log = event.snapshot.agent_log.map((msg, idx) => {
            if (!logTimestamps[idx]) {
              logTimestamps[idx] = new Date().toLocaleTimeString([], { hour12: false });
            }
            return `[${logTimestamps[idx]}] ${msg}`;
          });

          startTransition(() => {
            setResearchState(event.snapshot);
            // Sync selector if agent auto-detected a dataset
            if (event.snapshot.selected_dataset_path && !selectedDatasetPath) {
              setSelectedDatasetPath(event.snapshot.selected_dataset_path);
            }
          });

          if (event.type === "start") {
            setStatusText("Running agents...");
          }

          if (event.type === "update") {
            setStatusText(`${event.node ?? "Agent"} finished`);
          }

          if (event.type === "complete") {
            setStatusText("Research complete");
            setActiveTab("report");
          }

          if (event.type === "error") {
            setStatusText("Research stopped with an error");
            setNotice({
              tone: "error",
              message: event.message ?? "The API stream reported an error.",
            });
            setActiveTab("activity");
          }
        }

        if (done) {
          break;
        }
      }
    } catch (error) {
      setNotice({
        tone: "error",
        message: error instanceof Error ? error.message : "Research failed.",
      });
      setStatusText("Research failed");
    } finally {
      setIsResearching(false);
      await refreshDatasets().catch(() => undefined);
    }
  }

  return (
    <div className={`workspace-shell ${sidebarOpen ? 'sidebar-expanded' : ''}`}>
      <button 
        className="mobile-toggle" 
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label="Toggle Sidebar"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {notice && (
        <div className={`toast-notification ${notice.tone}`}>
          <div className="toast-content">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {notice.tone === 'success' ? (
                <>
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </>
              ) : (
                <>
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </>
              )}
            </svg>
            <span>{notice.message}</span>
          </div>
          <button className="toast-close" onClick={() => setNotice(null)}>&times;</button>
        </div>
      )}

      <Sidebar 
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        datasetRequest={datasetRequest}
        setDatasetRequest={setDatasetRequest}
        isGeneratingDataset={isGeneratingDataset}
        onGenerateDataset={handleGenerateDataset}
        isUploadingDataset={isUploadingDataset}
        onUploadDataset={handleUploadDataset}
        fileInputRef={fileInputRef}
        selectedDatasetPath={selectedDatasetPath}
        setSelectedDatasetPath={setSelectedDatasetPath}
        datasets={datasets}
        lastGeneratedDataset={lastGeneratedDataset}
      />

      {sidebarOpen && (
        <div 
          className="sidebar-backdrop" 
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <main className="main-stage">
        <section className="hero">
          <p className="eyebrow">Local Research Workspace</p>
          <h1>Multi-Agent Research Assistant</h1>
          <p className="hero-copy">
            A cleaner research surface for planning, dataset generation, retrieval, and Python execution on your machine.
          </p>
          <div className="chip-row">
            <span className="chip">{config?.llm_model ?? "Model loading"}</span>
            <span className="chip">{config?.embedding_model ?? "Embeddings loading"}</span>
            <span className="chip">{selectedDataset?.name ?? "Auto-detect dataset"}</span>
            <span className="chip">{statusText}</span>
          </div>
        </section>

        <Composer 
          query={query}
          setQuery={setQuery}
          exampleQuery={EXAMPLE_QUERY}
          isResearching={isResearching}
          isBootstrapping={isBootstrapping}
          onRun={handleRunResearch}
        />

        <MetricsGrid researchState={researchState} />

        <ResultsPanel 
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          researchState={{
            ...researchState,
            agent_log: researchState.agent_log.slice(logOffset)
          }}
          deferredReport={deferredReport}
          datasetPreview={datasetPreview}
          isPreviewLoading={isPreviewLoading}
          previewError={previewError}
          onClearLogs={handleClearLogs}
          apiBase={API_BASE}
        />
      </main>
    </div>
  );
}
