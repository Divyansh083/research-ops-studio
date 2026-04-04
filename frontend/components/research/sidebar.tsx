"use client";

import { ChangeEvent, RefObject } from "react";
import { DatasetRecord, DatasetArtifact } from "../../types/research";
import { CustomSelect } from "../ui/custom-select";
import { formatDatasetOption } from "../../lib/utils";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { Input } from "../ui/input";

interface SidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (val: boolean) => void;
  datasetRequest: string;
  setDatasetRequest: (val: string) => void;
  isGeneratingDataset: boolean;
  onGenerateDataset: () => void;
  isUploadingDataset: boolean;
  onUploadDataset: (event: ChangeEvent<HTMLInputElement>) => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  selectedDatasetPath: string | null;
  setSelectedDatasetPath: (path: string | null) => void;
  datasets: DatasetRecord[];
  lastGeneratedDataset: DatasetArtifact | null;
}

export function Sidebar({
  sidebarOpen,
  setSidebarOpen,
  datasetRequest,
  setDatasetRequest,
  isGeneratingDataset,
  onGenerateDataset,
  isUploadingDataset,
  onUploadDataset,
  fileInputRef,
  selectedDatasetPath,
  setSelectedDatasetPath,
  datasets,
  lastGeneratedDataset
}: SidebarProps) {
  return (
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
      <div className="sidebar-header">
        <Card variant="sidebar" className="branding-card">
          <div className="neural-logo-container">
            <svg className="neural-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2">
              <rect x="2" y="2" width="20" height="8" rx="1" />
              <rect x="2" y="14" width="20" height="8" rx="1" />
              <line x1="6" y1="10" x2="6" y2="14" />
              <line x1="18" y1="10" x2="18" y2="14" />
            </svg>
            <p className="eyebrow">Project Intelligence</p>
          </div>
          <h2 className="app-logo-text logo-pulse">NEURAL ARCHIVE</h2>
          <p className="muted small">Recursive Knowledge Engine</p>
        </Card>
      </div>

      <div className="sidebar-scroll-area">
        <Card variant="sidebar">
          <div className="form-section">
            <textarea
              className="sidebar-textarea"
              value={datasetRequest}
              onChange={(event) => setDatasetRequest(event.target.value)}
              placeholder="Describe your dataset needs (e.g. Sales data for 2023 with monthly targets)."
              aria-label="Dataset generation request"
              disabled={isGeneratingDataset}
            />
            
            <div className="button-group">
              <Button 
                variant="primary" 
                onClick={onGenerateDataset} 
                isLoading={isGeneratingDataset}
              >
                Generate CSV
              </Button>
              
              <input
                ref={fileInputRef}
                id="dataset-upload-input"
                type="file"
                accept=".csv"
                onChange={onUploadDataset}
                hidden
                aria-hidden="true"
              />
              <Button
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
                isLoading={isUploadingDataset}
              >
                Upload CSV
              </Button>
            </div>
          </div>

          <div className="form-section">
            <CustomSelect
              label="Active dataset"
              value={selectedDatasetPath ?? ""}
              options={[
                { value: "", label: formatDatasetOption("__auto_dataset__") },
                ...datasets.map(d => ({ value: d.path, label: formatDatasetOption(d.path) }))
              ]}
              onChange={(val) => setSelectedDatasetPath(val || null)}
            />
          </div>

          {lastGeneratedDataset ? (
            <div className="form-section">
              <Card variant="mini">
                <div className="mini-card-title">Last generated dataset</div>
                <p>{lastGeneratedDataset.summary ?? "Dataset prepared."}</p>
                {lastGeneratedDataset.columns?.length ? (
                  <p className="muted">
                    Columns: {lastGeneratedDataset.columns.join(", ")}
                  </p>
                ) : null}
              </Card>
            </div>
          ) : null}
        </Card>
      </div>
    </aside>
  );
}
