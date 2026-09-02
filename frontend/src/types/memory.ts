export type ProjectionStatus = "NOT_REQUIRED" | "PENDING" | "STAGED" | "FINALIZING" | "ACTIVE" | "RETIRED" | "FAILED";

export interface MemoryMutationHistory {
  mutation_id: string;
  decision: "CREATE" | "MERGE" | "REPLACE" | "REJECT" | "CONFLICT_REVIEW" | "NOOP";
  status: string;
  before_version: number | null;
  after_version: number | null;
  vector_status: ProjectionStatus;
  graph_status: ProjectionStatus;
  reason_code: string | null;
  error_code: string | null;
  error_summary: string | null;
  created_at: string;
  completed_at?: string | null;
  source_type?: string;
  source_id?: string;
  operator_id?: string;
  incoming_confidence?: string;
}

export interface MemoryEvidenceSummary {
  evidence_id: string;
  source_type: string;
  source_id: string;
  summary: string | null;
  observed_at: string;
  confidence: string;
}

export interface SharedMemoryFactDetail {
  fact_key: string;
  category?: string;
  fact_kind?: string;
  subject_type?: string;
  subject_id?: string;
  predicate?: string;
  object_type?: string | null;
  object_id?: string | null;
  version: number;
  confidence: string;
  status: string;
  expires_at: string | null;
  vector_memory_id?: string | null;
  graph_fact_key?: string | null;
  last_mutation_id?: string;
  updated_at?: string;
  value_json: Record<string, unknown>;
  projection_incomplete: boolean;
  mutations: MemoryMutationHistory[];
  evidence: MemoryEvidenceSummary[];
}
