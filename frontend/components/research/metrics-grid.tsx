"use client";

import { useMemo } from "react";
import { ResearchSnapshot } from "../../types/research";
import { Card } from "../ui/card";

interface MetricsGridProps {
  researchState: ResearchSnapshot;
}

export function MetricsGrid({ researchState }: MetricsGridProps) {
  const successfulCodeRuns = useMemo(
    () => researchState.code_outputs.filter((item) => item.status === "success").length,
    [researchState.code_outputs],
  );

  return (
    <section className="metrics-grid">
      <Card variant="metric">
        <span className="metric-label">Planned tasks</span>
        <strong>{researchState.subtasks.length}</strong>
      </Card>
      <Card variant="metric">
        <span className="metric-label">Completed</span>
        <strong>{researchState.completed_subtasks.length}</strong>
      </Card>
      <Card variant="metric">
        <span className="metric-label">Evidence items</span>
        <strong>
          {researchState.search_results.length + 
           researchState.rag_results.length + 
           researchState.dataset_outputs.length}
        </strong>
      </Card>
      <Card variant="metric">
        <span className="metric-label">Code runs</span>
        <strong>
          {successfulCodeRuns}/{researchState.code_outputs.length}
        </strong>
      </Card>
    </section>
  );
}
