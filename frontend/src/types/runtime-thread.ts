export interface RuntimeThreadDetail {
  thread_id: string;
  task_id: string;
  status: "RUNNING" | "STABLE" | "TERMINAL";
  terminal: boolean;
  current_checkpoint_id: string | null;
  state_version: number;
  current_node: string | null;
  next_node: string | null;
  checkpoint_count: number;
  checkpoint_size_bytes: number | null;
  last_event_sequence: number | null;
  worker_consumer: string | null;
  checkpoint_available: boolean;
  state: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  terminal_at: string | null;
}

export interface RuntimeCheckpointHistoryItem {
  checkpoint_id: string;
  state_version: number;
  parent_checkpoint_id?: string | null;
  node?: string | null;
  next_node?: string | null;
  checkpoint_size_bytes?: number | null;
  checkpoint_available?: boolean | null;
  created_at?: string | null;
}

export interface RuntimeThreadHistory {
  thread_id: string;
  items: RuntimeCheckpointHistoryItem[];
}
