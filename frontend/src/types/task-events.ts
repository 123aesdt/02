export interface TaskEvent {
  event_id: string;
  task_id: string;
  event_type: string;
  node: string;
  status: string;
  timestamp: string;
  sequence: number;
  data: Record<string, unknown>;
}
