const API_BASE = '/api/v1';

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (!response.ok) {
    let code = 'unknown';
    let message = `HTTP ${response.status}`;
    let details: unknown;
    try {
      const body = await response.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
      details = body?.error?.details;
    } catch {
      // Non-JSON error response
    }
    throw new ApiError(response.status, code, message, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

export { ApiError };

// --- Type definitions ---
export interface ConnectionResponse {
  id: string;
  name: string;
  provider_type: string;
  endpoint: string;
  auth_method: string;
  default_workdir: string | null;
  enabled: boolean;
  capabilities_cache: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
  capabilities: Record<string, unknown> | null;
  version: string | null;
}

export interface SandboxInfo {
  sandbox_id: string;
  connection_id: string | null;
  name: string;
  state: string;
  image: string | null;
  workdir: string;
  expires_at: string | null;
  created_at: string | null;
  last_activity_at: string | null;
  metadata: Record<string, string>;
}

export interface SandboxListResponse {
  items: SandboxInfo[];
  total: number;
  next_page_token: string | null;
}

export interface LoginResponse {
  session_token: string;
  actor_id: string;
  auth_method: string;
  expires_at: string;
}

export interface ActorInfo {
  actor_id: string;
  auth_method: string;
}

// --- File types ---
export interface FileEntry {
  path: string;
  kind: 'file' | 'directory' | 'symlink' | 'other';
  size: number;
  content_hash: string | null;
}

export interface FileListResponse {
  path: string;
  entries: FileEntry[];
}

export interface FileContent {
  path: string;
  content: string;
  content_hash: string;
  size: number;
  is_binary: boolean;
}

export interface FileWriteResult {
  path: string;
  content_hash: string;
  size: number;
  previous_hash: string | null;
}

// --- Command types ---
export interface CommandCreateRequest {
  command: string;
  cwd?: string;
  env?: Record<string, string>;
  timeout_seconds?: number;
  mode?: 'foreground' | 'background';
}

export interface CommandCreateResponse {
  command_id: string;
  status: string;
  mode: string;
}

export interface CommandResponse {
  command_id: string;
  status: string;
  exit_code: number | null;
  duration_ms: number | null;
  stdout: string;
  stderr: string;
  command: string;
  cwd: string | null;
  mode: string;
}

export interface Capabilities {
  [key: string]: {
    supported: boolean;
    strength: string;
    limits: Record<string, unknown>;
    reason: string | null;
    source: string;
  };
}

// --- History types ---
export interface HistoryEvent {
  event_id: string;
  source_seq: number;
  source: string;
  actor_type: string;
  actor_id: string | null;
  thread_id: string | null;
  run_id: string | null;
  operation_type: string;
  status: string;
  occurred_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  command: string | null;
  cwd: string | null;
  exit_code: number | null;
  file_path: string | null;
  file_change_type: string | null;
  before_hash: string | null;
  after_hash: string | null;
  before_size: number | null;
  after_size: number | null;
  output_complete: number;
  history_storage_state: string;
}

export interface HistoryResponse {
  coverage: string;
  source: string;
  helper_status: string;
  items: HistoryEvent[];
  total: number;
  last_synced_at: string | null;
}

export interface HistoryEventDetail {
  event: HistoryEvent;
  stdout: string | null;
  stderr: string | null;
  request: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
}

export interface HistoryAvailability {
  available: boolean;
  reason: string | null;
  last_synced_at: string | null;
}

export interface TerminalCreateResponse {
  terminal_id: string;
  ws_url: string;
}

// --- Backup types ---
export interface BackupItem {
  backup_id: string;
  file_path: string;
  content_hash: string;
  content_size: number;
  encoding: string;
  original_size: number;
  description: string;
  trigger_type: string;
  rule_name: string | null;
  actor_type: string;
  actor_id: string | null;
  command: string | null;
  created_at: string;
}

export interface BackupDetail extends BackupItem {
  content_base64: string | null;
}

export interface BackupListResponse {
  backups: BackupItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface BackupFileListResponse {
  files: { file_path: string; backup_count: number; latest_backup_at: string }[];
  total: number;
}

export interface BackupCreateResponse {
  backup_id: string | null;
  file_path: string;
  created: boolean;
  message: string | null;
}

export interface BackupRestoreResponse {
  backup_id: string;
  file_path: string;
  content_hash: string;
  content_size: number;
  restored: boolean;
  pre_restore_backup_id: string | null;
  message: string | null;
}

export interface BackupDeleteResponse {
  backup_id: string;
  deleted: boolean;
}

export interface BackupDeleteByPathResponse {
  file_path: string;
  deleted: number;
}

export interface BackupDiffResponse {
  backup_id: string;
  file_path: string;
  diff: string | null;
  has_diff: boolean;
  comparison_source: string;
  is_binary: boolean;
  is_latest: boolean;
  old_text: string | null;
  new_text: string | null;
}

export interface BackupBatchDeleteResponse {
  deleted: number;
  failed: number;
  details: { backup_id: string; deleted: boolean; error?: string }[];
}

// --- Policy types ---
export interface PolicyGroup {
  id: string;
  name: string;
  description: string;
  version: number;
  enabled: boolean;
  rule_count: number;
  registration_count: number;
  created_at: string;
  updated_at: string;
}

export interface PolicyRule {
  id: string;
  group_id: string;
  sandbox_id: string | null;
  rule_type: 'command' | 'workspace';
  pattern: string;
  effect: 'allow' | 'deny';
  operations: string;
  priority: number;
  description: string;
  is_baseline: boolean;
  created_at: string;
  updated_at: string;
}

export interface SdkRegistration {
  id: string;
  group_id: string;
  sandbox_id: string;
  sandbox_name: string | null;
  agent_name: string | null;
  sdk_version: string;
  callback_url: string | null;
  callback_mode: string;
  last_seen: string;
  online: boolean;
}

export interface SandboxLookupResponse {
  sandbox_id: string;
  sandbox_instance_id: string;
  provider_name: string;
  provider_key: string;
  agent_name: string | null;
}

// --- Dashboard types ---
export interface DashboardOverview {
  connections: { total: number; enabled: number };
  sandboxes: { total: number; by_state: Record<string, number> };
  workspaces: { total: number; active: number };
  policy_groups: { total: number; enabled: number };
  policy_rules: { total: number; allow: number; deny: number };
  agents: { total: number; online: number };
  operations: {
    total: number;
    by_type: Record<string, number>;
    by_status: Record<string, number>;
    by_source: Record<string, number>;
    by_actor: { actor_id: string; count: number }[];
    recent: RecentOperation[];
  };
  sandbox_summaries: {
    sandbox_id: string;
    connection_id: string | null;
    name: string;
    state: string;
    image: string | null;
    created_at: string | null;
    last_activity_at: string | null;
  }[];
}

export interface RecentOperation {
  event_id: string;
  connection_id: string;
  sandbox_id: string;
  source: string;
  actor_type: string;
  actor_id: string | null;
  operation_type: string;
  status: string;
  occurred_at: string;
  duration_ms: number | null;
  command: string | null;
  file_path: string | null;
}
