"use client";

import React from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ResearchSnapshot } from "../../types/research";
import { formatAgentLabel, formatStatus } from "../../lib/utils";
import { Card } from "../ui/card";
import { Tabs } from "../ui/tabs";

interface ResultsPanelProps {
  activeTab: "report" | "activity" | "dataset" | "artifacts";
  setActiveTab: (tab: "report" | "activity" | "dataset" | "artifacts") => void;
  researchState: ResearchSnapshot;
  deferredReport: string | null;
  datasetPreview: { columns: string[]; data: any[] } | null;
  isPreviewLoading: boolean;
  previewError: string | null;
  onClearLogs: () => void;
  apiBase: string;
}

const TABS = ["report", "activity", "dataset", "artifacts"] as const;

export function ResultsPanel({
  activeTab,
  setActiveTab,
  researchState,
  deferredReport,
  datasetPreview,
  isPreviewLoading,
  previewError,
  onClearLogs,
  apiBase
}: ResultsPanelProps) {
  const logContainerRef = React.useRef<HTMLDivElement>(null);
  const [isMounted, setIsMounted] = React.useState(false);

  React.useEffect(() => {
    setIsMounted(true);
  }, []);

  // Auto-scroll to bottom when logs change
  React.useEffect(() => {
    if (activeTab === "activity" && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [researchState.agent_log, activeTab, isMounted]);

  return (
    <>
      <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === "report" && (
        <div 
          role="tabpanel" 
          id="panel-report" 
          aria-labelledby="tab-report"
          tabIndex={0}
        >
          <Card variant="panel" style={{ position: 'relative', overflow: 'hidden' }}>
            <p className="eyebrow">Final Report</p>
            {(() => {
              if (!deferredReport) {
                return (
                  <div className="empty-state">
                    Your finished report will appear here after the research run completes.
                  </div>
                );
              }
              
              if (deferredReport.includes("Rate Limit Exceeded")) {
                const dialogContent = (
                  <div style={{
                    position: 'fixed',
                    top: 0, left: 0, right: 0, bottom: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'rgba(19, 19, 24, 0.85)', /* match surface */
                    backdropFilter: 'blur(12px)',
                    zIndex: 999999,
                    animation: 'backdropFade 600ms ease-in-out forwards'
                  }}>
                    <div style={{
                      background: 'var(--surface-container-high)',
                      border: '1px solid rgba(0, 240, 255, 0.15)',
                      boxShadow: '0 10px 40px rgba(0, 0, 0, 0.5), 0 0 50px rgba(0, 240, 255, 0.05)',
                      padding: '3rem',
                      maxWidth: '550px',
                      width: '90%',
                      textAlign: 'center',
                      position: 'relative',
                      overflow: 'hidden',
                      borderRadius: '12px',
                      animation: 'premiumFadeScale 600ms cubic-bezier(0.16, 1, 0.3, 1) forwards'
                    }}>
                      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', background: 'repeating-linear-gradient(rgba(0,255,255,0.03) 0px, transparent 1px, transparent 2px)', backgroundSize: '100% 3px', zIndex: 0 }}></div>
                      
                      <div style={{ position: 'relative', zIndex: 1 }}>
                        <div style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: '64px', height: '64px',
                          borderRadius: '50%',
                          background: 'rgba(0, 240, 255, 0.05)',
                          border: '1px solid rgba(0, 240, 255, 0.2)',
                          color: 'var(--primary)',
                          marginBottom: '1.5rem',
                          boxShadow: '0 0 20px rgba(0, 240, 255, 0.1)'
                        }}>
                          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: 'translateY(-1px)' }}>
                            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                            <line x1="12" y1="9" x2="12" y2="13" />
                            <line x1="12" y1="17" x2="12.01" y2="17" />
                          </svg>
                        </div>
                        
                        <h2 style={{ color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '3px', marginBottom: '1rem', fontSize: '1.5rem', fontFamily: 'var(--font-space-grotesk)' }}>
                          Rate Limit Exceeded
                        </h2>
                        
                        <p style={{ color: '#b9cacb', marginBottom: '2.5rem', lineHeight: 1.6, fontSize: '1rem' }}>
                          The AI model API has reached its token limits. The research run has been vaulted to prevent data corruption. Please wait a few minutes or switch to an alternate model.
                        </p>
                        
                        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
                          <button 
                            onClick={() => setActiveTab('activity')}
                            style={{
                              background: 'transparent',
                              border: '1px solid var(--ghost-border)',
                              color: '#b9cacb',
                              padding: '0.75rem 1.5rem',
                              cursor: 'pointer',
                              textTransform: 'uppercase',
                              letterSpacing: '2px',
                              fontSize: '0.75rem',
                              fontWeight: 'bold',
                              transition: 'all 0.2s',
                              borderRadius: '4px'
                            }}
                            onMouseOver={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = '#fff' }}
                            onMouseOut={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#b9cacb' }}
                          >
                            View Logs
                          </button>
                          <button 
                            onClick={() => window.location.reload()}
                            style={{
                              background: 'var(--primary)',
                              border: 'none',
                              color: '#002022',
                              padding: '0.75rem 1.5rem',
                              cursor: 'pointer',
                              textTransform: 'uppercase',
                              letterSpacing: '2px',
                              fontSize: '0.75rem',
                              fontWeight: 'bold',
                              boxShadow: '0 0 15px rgba(0, 240, 255, 0.4)',
                              transition: 'all 0.2s',
                              borderRadius: '4px'
                            }}
                            onMouseOver={(e) => { e.currentTarget.style.boxShadow = '0 0 25px rgba(0, 240, 255, 0.8)'; e.currentTarget.style.transform = 'scale(1.02)' }}
                            onMouseOut={(e) => { e.currentTarget.style.boxShadow = '0 0 15px rgba(0, 240, 255, 0.4)'; e.currentTarget.style.transform = 'scale(1)' }}
                          >
                            Acknowledge
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
                
                return isMounted ? createPortal(dialogContent, document.body) : null;
              }
              
              return (
                <article>
                  <div className="report-content report-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{deferredReport}</ReactMarkdown>
                    
                    {researchState.code_outputs?.some(c => c.artifacts?.length) && (
                      <div className="report-plots">
                        <h2 className="mt-8 mb-6">Generated Visualizations</h2>
                        <div className="plot-gallery">
                          {researchState.code_outputs.flatMap(c => c.artifacts || [])
                            .filter(file => /\.(png|jpg|jpeg|gif|webp|svg)$/i.test(file))
                            .map((file, idx) => (
                              <img
                                key={`report-plot-${file}-${idx}`}
                                src={`${apiBase}/api/sandbox/files/${file}`}
                                alt={`Generated plot ${idx + 1}`}
                                className="plot-image"
                              />
                            ))}
                        </div>
                      </div>
                    )}
                  </div>
                </article>
              );
            })()}
          </Card>
        </div>
      )}

      {activeTab === "activity" && (
        <div 
          role="tabpanel" 
          id="panel-activity" 
          aria-labelledby="tab-activity"
          tabIndex={0}
        >
          <Card variant="panel" style={{ position: 'relative' }}>
            {/* Terminal Scanline Overlay */}
            <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', background: 'repeating-linear-gradient(rgba(0,255,255,0.03) 0px, transparent 1px, transparent 2px)', backgroundSize: '100% 3px', zIndex: 10 }}></div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '1rem' }}>
              <div>
                <p className="eyebrow" style={{ margin: 0 }}>Agent Activity</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#00ffff', boxShadow: '0 0 8px #00ffff', animation: 'pulse 2s infinite' }}></span>
                  <span style={{ fontSize: '0.625rem', color: '#00ffff', fontWeight: 'bold', letterSpacing: '1px' }}>LIVE_STREAM</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                <button 
                  onClick={() => {
                    if (confirm("Clear all activity logs? This cannot be undone.")) {
                      onClearLogs();
                    }
                  }}
                  style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.1)', color: '#adaaab', fontSize: '0.5625rem', padding: '0.25rem 0.75rem', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px', cursor: 'pointer' }}
                >
                  Clear
                </button>
                <button 
                  onClick={() => {
                    const logContent = researchState.agent_log.join('\n');
                    const blob = new Blob([logContent], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `agent_activity_${new Date().toISOString().split('T')[0]}.txt`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  style={{ background: 'rgba(0,255,255,1)', border: '1px solid rgba(0,255,255,0.2)', color: '#004343', fontSize: '0.5625rem', padding: '0.25rem 0.75rem', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px', cursor: 'pointer' }}
                >
                  Export
                </button>
              </div>
            </div>

            {isMounted && researchState.agent_log.length > 0 ? (
              <div 
                className="log-container" 
                ref={logContainerRef}
                style={{ 
                  height: 'clamp(300px, 60vh, 500px)', 
                  overflowY: 'auto', 
                  overflowX: 'hidden',
                  paddingRight: '0.5rem', 
                  fontFamily: 'monospace',
                  scrollBehavior: 'smooth',
                  width: '100%'
                }}
              >
                {researchState.agent_log.map((log, idx) => {
                  let logTypeColor = '#00ffff'; // Default Cyan
                  let typeLabel = '[ INFO ]';
                  
                  if (log.toLowerCase().includes('error')) { logTypeColor = '#ff716c'; typeLabel = '[ ERROR ]'; }
                  else if (log.toLowerCase().includes('warning')) { logTypeColor = '#facc15'; typeLabel = '[ WARN ]'; }
                  else if (log.toLowerCase().includes('success') || log.toLowerCase().includes('completed')) { logTypeColor = '#4ade80'; typeLabel = '[ OKAY ]'; }
                  else if (log.toLowerCase().includes('system')) { logTypeColor = '#ff66ff'; typeLabel = '[ SYS ]'; }

                  // The log already contains the timestamp in [HH:MM:SS] format from workspace
                  const timeMatch = log.match(/^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$/);
                  const displayTime = timeMatch ? timeMatch[1] : '00:00:00';
                  const displayLog = timeMatch ? timeMatch[2] : log;

                  return (
                    <div key={`log-${idx}`} className="log-entry" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem 1rem', padding: '0.5rem', borderLeft: `2px solid ${logTypeColor}33`, marginBottom: '2px', background: idx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent', transition: 'background 0.2s', width: '100%' }} onMouseOver={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')} onMouseOut={(e) => (e.currentTarget.style.background = idx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent')}>
                      <div style={{ display: 'flex', gap: '1rem', flexShrink: 0 }}>
                        <span suppressHydrationWarning style={{ width: '64px', flexShrink: 0, fontSize: '0.75rem', color: '#767576', borderRight: '1px solid rgba(255,255,255,0.05)', paddingRight: '0.5rem' }}>
                          {displayTime}
                        </span>
                        <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: logTypeColor, width: '60px', flexShrink: 0 }}>{typeLabel}</span>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: '#ffffff', opacity: 0.9, lineHeight: '1.4', wordBreak: 'break-word', flex: 1, minWidth: '200px' }}>{displayLog}</span>
                    </div>
                  );
                })}
                <div id="log-end" />
              </div>
            ) : (
              <div className="empty-state" style={{ height: '500px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {isMounted ? "No agent activity logged yet. Standby for initialization..." : "Initializing stream..."}
              </div>
            )}
          </Card>
        </div>
      )}

      {activeTab === "dataset" && (
        <div 
          role="tabpanel" 
          id="panel-dataset" 
          aria-labelledby="tab-dataset"
          tabIndex={0}
        >
          <Card variant="panel" style={{ padding: '0', border: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ padding: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.01)' }}>
              <p className="eyebrow" style={{ margin: 0 }}>Dataset Preview</p>
              <div style={{ height: '2px', width: '40px', background: 'var(--primary)', marginTop: '0.5rem', boxShadow: '0 0 8px var(--primary)' }}></div>
            </div>
            
            {isMounted && isPreviewLoading ? (
              <div className="loading-state" style={{ padding: '4rem', textAlign: 'center', color: 'var(--primary)', fontFamily: 'var(--font-space-grotesk)', letterSpacing: '2px' }}>
                <div style={{ animation: 'pulse 1.5s infinite', fontSize: '0.75rem', fontWeight: 'bold' }}>INITIALIZING_DATA_STREAM...</div>
              </div>
            ) : isMounted && datasetPreview ? (
              <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch', height: 'clamp(300px, 60vh, 500px)', width: '100%', position: 'relative' }}>
                <table style={{ width: '100%', minWidth: '800px', borderCollapse: 'collapse', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                  <thead style={{ position: 'sticky', top: 0, zIndex: 20, background: 'var(--surface-container-highest)', boxShadow: '0 2px 10px rgba(0,0,0,0.3)' }}>
                    <tr>
                      {datasetPreview.columns.map((col) => (
                        <th key={`th-${col}`} style={{ padding: '1rem', textAlign: 'left', color: '#00ffff', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px', borderBottom: '2px solid rgba(0,255,255,0.1)' }}>
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {datasetPreview.data.map((row, rIdx) => (
                      <tr 
                        key={`tr-${rIdx}`} 
                        style={{ 
                          background: rIdx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                          transition: 'all 0.2s ease',
                          borderBottom: '1px solid rgba(255,255,255,0.03)'
                        }}
                        onMouseOver={(e) => {
                          e.currentTarget.style.background = 'rgba(0, 255, 255, 0.05)';
                          e.currentTarget.style.boxShadow = 'inset 0 0 10px rgba(0, 255, 255, 0.05)';
                        }}
                        onMouseOut={(e) => {
                          e.currentTarget.style.background = rIdx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent';
                          e.currentTarget.style.boxShadow = 'none';
                        }}
                      >
                        {datasetPreview.columns.map((col) => (
                          <td key={`td-${rIdx}-${col}`} style={{ padding: '0.875rem 1rem', color: '#ffffff', opacity: 0.8 }}>
                            {String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state" style={{ height: '500px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: 0.5, textAlign: 'center', fontSize: '0.875rem' }}>
                {previewError ? (
                  <div style={{ color: '#ff716c', padding: '2rem', border: '1px dashed rgba(255,113,108,0.3)', borderRadius: '4px', background: 'rgba(255,113,108,0.05)' }}>
                    <div style={{ fontWeight: 'bold', marginBottom: '0.5rem', letterSpacing: '1px' }}>PREVIEW_PIPELINE_ERROR</div>
                    <div style={{ fontSize: '0.75rem', maxWidth: '300px' }}>{previewError}</div>
                  </div>
                ) : isMounted ? (
                  "Select or generate a dataset to initiate neural preview."
                ) : (
                  "Initializing dataset..."
                )}
              </div>
            )}
          </Card>
        </div>
      )}

      {activeTab === "artifacts" && (
        <div 
          role="tabpanel" 
          id="panel-artifacts" 
          aria-labelledby="tab-artifacts"
          tabIndex={0}
        >
          <Card variant="panel">
            <p className="eyebrow">Research Artifacts</p>
          <div className="artifacts-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))', gap: '1.5rem' }}>
              {researchState.dataset_outputs.map((dataset, idx) => (
                <Card variant="artifact" key={`artifact-ds-${idx}`} style={{ position: 'relative', overflow: 'hidden', padding: '1.5rem', border: '1px solid rgba(255,255,255,0.05)', transition: 'border-color 0.3s ease' }} onMouseOver={(e) => (e.currentTarget.style.borderColor = 'rgba(0, 255, 255, 0.3)')} onMouseOut={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)')}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                    <span style={{ background: 'rgba(0, 255, 255, 0.1)', color: '#00ffff', fontSize: '0.625rem', padding: '0.2rem 0.5rem', fontWeight: 'bold', letterSpacing: '1px', borderRadius: '2px', border: '1px solid rgba(0, 255, 255, 0.3)' }}>DATASET</span>
                    <span style={{ fontSize: '0.625rem', fontFamily: 'monospace', color: '#adaaab' }}>
                      FORMAT: {dataset.path?.split('.').pop()?.toUpperCase() || 'UNKNOWN'}
                    </span>
                  </div>
                  <div style={{ fontFamily: 'var(--font-space-grotesk)', fontSize: '1.25rem', color: '#c1fffe', marginBottom: '0.5rem' }}>
                    {dataset.path?.split(/[\\/]/).pop() || "unknown.csv"}
                  </div>
                  <p style={{ color: '#adaaab', fontSize: '0.875rem', lineHeight: '1.6', marginBottom: '2rem' }}>{dataset.summary}</p>
                  
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '1.5rem', marginTop: 'auto' }}>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: '0.5625rem', color: '#767576', textTransform: 'uppercase', letterSpacing: '2px', fontWeight: 'bold', marginBottom: '0.25rem' }}>Row count</span>
                      <span style={{ fontFamily: 'monospace', color: '#00ffff', fontSize: '0.875rem' }}>{dataset.row_count}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(0, 255, 255, 0.05)', padding: '0.25rem 0.75rem', borderRadius: '999px', border: '1px solid rgba(0, 255, 255, 0.2)', boxShadow: '0 0 10px rgba(0,255,255,0.05)' }}>
                      <span style={{ fontSize: '0.625rem', fontWeight: 'bold', color: '#00ffff', letterSpacing: '2px', textTransform: 'uppercase' }}>
                        {['completed', 'success', 'created'].includes(dataset.status?.toLowerCase() || '') ? 'VERIFIED' : dataset.status}
                      </span>
                    </div>
                  </div>
                </Card>
              ))}
              {researchState.code_outputs.map((code, idx) => (
                <React.Fragment key={`artifact-code-group-${idx}`}>
                  <Card variant="artifact" className="code" style={{ position: 'relative', overflow: 'hidden', padding: '1.5rem', border: '1px solid rgba(255,255,255,0.05)', transition: 'border-color 0.3s ease' }} onMouseOver={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 102, 255, 0.3)')} onMouseOut={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)')}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                      <span style={{ background: 'rgba(255, 102, 255, 0.1)', color: '#ff66ff', fontSize: '0.625rem', padding: '0.2rem 0.5rem', fontWeight: 'bold', letterSpacing: '1px', borderRadius: '2px', border: '1px solid rgba(255, 102, 255, 0.3)' }}>PYTHON_EXECUTION</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: ['completed', 'success'].includes(code.status?.toLowerCase() || '') ? '#4ade80' : '#ff716c', boxShadow: `0 0 8px ${['completed', 'success'].includes(code.status?.toLowerCase() || '') ? '#4ade80' : '#ff716c'}` }}></span>
                        <span style={{ fontSize: '0.625rem', fontWeight: 'bold', color: ['completed', 'success'].includes(code.status?.toLowerCase() || '') ? '#4ade80' : '#ff716c', letterSpacing: '2px', textTransform: 'uppercase' }}>
                          {['completed', 'success'].includes(code.status?.toLowerCase() || '') ? 'SUCCESS' : code.status}
                        </span>
                      </div>
                    </div>
                    <div style={{ fontFamily: 'var(--font-space-grotesk)', fontSize: '1.25rem', color: '#ffbdff', marginBottom: '1rem' }}>
                      Code Run #{idx + 1}
                    </div>
                    <div style={{ background: 'rgba(0,0,0,0.5)', padding: '1rem', borderRadius: '2px', borderLeft: '2px solid rgba(255, 102, 255, 0.5)', marginBottom: '1.5rem', overflowX: 'auto' }}>
                      <pre style={{ fontFamily: 'monospace', fontSize: '0.75rem', lineHeight: '1.6', color: '#ffd1ff', opacity: 0.9 }}><code>{code.code}</code></pre>
                    </div>
                  </Card>
                  {code.artifacts?.map((file, fIdx) => {
                    const ext = file.split('.').pop()?.toUpperCase() || 'FILE';
                    const isImage = /\.(png|jpg|jpeg|gif|webp|svg)$/i.test(file);
                    const accentColor = isImage ? '#00ffff' : '#facc15';
                    
                    return (
                    <Card variant="artifact" className="file" key={`artifact-file-${idx}-${fIdx}`} style={{ position: 'relative', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
                        <div style={{ padding: '1.25rem', background: 'rgba(255,255,255,0.02)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', minWidth: 0, flex: 1 }}>
                            <div style={{ width: '2.5rem', height: '2.5rem', flexShrink: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(255,255,255,0.05)' }}>
                              <span style={{ fontSize: '0.625rem', fontWeight: 'bold', color: accentColor }}>{ext}</span>
                            </div>
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file}</div>
                              <div style={{ fontSize: '0.5625rem', color: '#767576', fontFamily: 'var(--font-space-grotesk)', textTransform: 'uppercase', letterSpacing: '1px', marginTop: '0.25rem' }}>Generated Output</div>
                            </div>
                          </div>
                          <a 
                            href={`${apiBase}/api/sandbox/files/${file}`} 
                            download
                            style={{ 
                              flexShrink: 0,
                              background: isImage ? '#c1fffe' : 'transparent', 
                              color: isImage ? '#004343' : accentColor, 
                              border: isImage ? 'none' : `1px solid ${accentColor}`, 
                              padding: '0.5rem 1rem', 
                              fontSize: '0.625rem', 
                              fontWeight: 'bold', 
                              letterSpacing: '2px', 
                              textDecoration: 'none', 
                              transition: 'all 0.3s ease', 
                              cursor: 'pointer', 
                              boxShadow: isImage ? '0 0 15px rgba(0,255,255,0.3)' : 'none'
                            }}
                          >
                            {isImage ? 'DOWNLOAD' : 'EXPORT'}
                          </a>
                        </div>
                      {isImage && (
                        <div style={{ height: '8rem', width: '100%', background: 'rgba(0,0,0,0.5)', overflow: 'hidden', position: 'relative', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                          <img src={`${apiBase}/api/sandbox/files/${file}`} alt={file} style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.6 }} />
                          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.6), transparent)' }}></div>
                        </div>
                      )}
                    </Card>
                  )})}
                </React.Fragment>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
