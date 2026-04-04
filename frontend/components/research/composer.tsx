"use client";

import { Button } from "../ui/button";
import { Card } from "../ui/card";

interface ComposerProps {
  query: string;
  setQuery: (val: string) => void;
  exampleQuery: string;
  isResearching: boolean;
  isBootstrapping: boolean;
  onRun: () => void;
}

export function Composer({ 
  query, 
  setQuery, 
  exampleQuery, 
  isResearching, 
  isBootstrapping, 
  onRun 
}: ComposerProps) {
  return (
    <Card variant="composer">
      <div className="composer-header">
        <div>
          <p className="eyebrow">Research Brief</p>
          <h2>Describe what you want done</h2>
        </div>
        <Button 
          variant="ghost" 
          onClick={() => setQuery(exampleQuery)}
          disabled={isResearching}
        >
          Use example
        </Button>
      </div>
      <textarea
        className="main-textarea"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Ask a research question, request a dataset analysis, or tell the app to write and execute Python for you."
        aria-label="Research query description"
        disabled={isResearching}
      />
      <div className="composer-footer">
        <Button 
          variant="primary" 
          size="large"
          className={isResearching ? "run-research-btn-active" : ""}
          onClick={onRun} 
          disabled={isResearching || isBootstrapping}
          isLoading={isResearching}
        >
          Run Research
        </Button>
      </div>
    </Card>
  );
}
