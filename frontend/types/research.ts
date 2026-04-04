export type DatasetRecord = {
  path: string;
  name: string;
  group: string;
  summary: string | null;
  row_count: number | null;
  columns: string[];
};

export type DatasetArtifact = {
  path?: string | null;
  source_query?: string;
  status?: string;
  summary?: string;
  note?: string | null;
  row_count?: number | null;
  columns?: string[];
};

export type SearchResult = {
  title: string;
  snippet: string;
  url: string;
};

export type RagResult = {
  content: string;
  source: string;
  score: number;
};

export type CodeOutput = {
  code: string;
  output: string;
  error?: string | null;
  status: string;
  note?: string | null;
  dataset_path?: string | null;
  dataset_source_path?: string | null;
  artifacts?: string[];
};

export type Subtask = {
  agent: string;
  subtask: string;
};

export type ResearchSnapshot = {
  query: string;
  subtasks: Subtask[];
  search_results: SearchResult[];
  rag_results: RagResult[];
  dataset_outputs: DatasetArtifact[];
  code_outputs: CodeOutput[];
  completed_subtasks: string[];
  summaries: string[];
  final_report: string | null;
  agent_log: string[];
  error_log: string[];
  selected_dataset_path?: string | null;
  available_datasets?: string[];
};

export type ConfigPayload = {
  llm_model: string;
  embedding_model: string;
  sandbox_ready: boolean;
  dataset_count: number;
  datasets: DatasetRecord[];
};

export type Notice = {
  tone: "success" | "error" | "info";
  message: string;
};

export const emptySnapshot: ResearchSnapshot = {
  query: "",
  subtasks: [],
  search_results: [],
  rag_results: [],
  dataset_outputs: [],
  code_outputs: [],
  completed_subtasks: [],
  summaries: [],
  final_report: null,
  agent_log: [],
  error_log: [],
  selected_dataset_path: null,
  available_datasets: [],
};
