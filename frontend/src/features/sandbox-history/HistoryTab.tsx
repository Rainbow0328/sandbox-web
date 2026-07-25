import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  X,
  Clock,
  User,
  Bot,
  Server,
  ShieldCheck,
  Terminal,
  FileText,
  Package,
  ChevronRight,
} from 'lucide-react';
import { api, type HistoryResponse, type HistoryEventDetail } from '@/lib/api';
import { cn } from '@/lib/utils';

interface HistoryTabProps {
  connectionId: string;
  sandboxId: string;
}

const sourceIcons: Record<string, typeof User> = {
  console: User,
  sdk: Bot,
  agent: Bot,
  provider: Server,
  gateway: Server,
};

const sourceLabels: Record<string, string> = {
  console: 'Console',
  sdk: 'SDK',
  agent: 'Agent',
  provider: 'Provider',
  gateway: 'Gateway',
};

const statusColors: Record<string, string> = {
  succeeded: 'bg-green-100 text-green-700 border-green-200',
  failed: 'bg-red-100 text-red-700 border-red-200',
  running: 'bg-blue-100 text-blue-700 border-blue-200',
  cancelled: 'bg-gray-100 text-gray-700 border-gray-200',
  timeout: 'bg-orange-100 text-orange-700 border-orange-200',
};

const operationIcons: Record<string, typeof Terminal> = {
  command: Terminal,
  command_finish: Terminal,
  file_write: FileText,
  file_read: FileText,
  file_delete: FileText,
  file_list: FileText,
  'sandbox.create': Package,
  'sandbox.delete': Package,
  'sandbox.pause': Package,
  'sandbox.resume': Package,
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function HistoryTab({ connectionId, sandboxId }: HistoryTabProps) {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterActor, setFilterActor] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const queryClient = useQueryClient();
  const hasAutoSynced = useRef(false);
  const lastSyncTs = useRef(0);

  // Auto-trigger history sync when the tab is first opened, and periodically
  // thereafter.  Uses a 60-second minimum interval to avoid flooding the
  // sandbox with helper commands.  The backend also has a 5-second throttle
  // as a second line of defense.
  useEffect(() => {
    const doSync = () => {
      const now = Date.now();
      if (now - lastSyncTs.current < 60_000) return;
      lastSyncTs.current = now;
      api
        .post(`/sandboxes/${connectionId}/${sandboxId}/history/sync`)
        .then(() => {
          queryClient.invalidateQueries({ queryKey: ['history', connectionId, sandboxId] });
        })
        .catch(() => {
          // Silent failure — sync is best-effort.
        });
    };
    // Sync on mount (first open).
    if (!hasAutoSynced.current) {
      hasAutoSynced.current = true;
      doSync();
    }
    // Sync every 60 seconds.
    const interval = setInterval(doSync, 60_000);
    return () => clearInterval(interval);
  }, [connectionId, sandboxId, queryClient]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['history', connectionId, sandboxId, filterType, filterStatus, filterActor, filterSource],
    queryFn: () => {
      const params = new URLSearchParams();
      if (filterType) params.set('operation_type', filterType);
      if (filterStatus) params.set('status', filterStatus);
      if (filterActor) params.set('actor_id', filterActor);
      if (filterSource) params.set('source', filterSource);
      const qs = params.toString();
      return api.get<HistoryResponse>(
        `/sandboxes/${connectionId}/${sandboxId}/history${qs ? `?${qs}` : ''}`,
      );
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const syncMutation = useMutation({
    mutationFn: () =>
      api.post(`/sandboxes/${connectionId}/${sandboxId}/history/sync`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history', connectionId, sandboxId] });
    },
  });

  const { data: eventDetail } = useQuery({
    queryKey: ['history-event', connectionId, sandboxId, selectedEventId],
    queryFn: () =>
      api.get<HistoryEventDetail>(
        `/sandboxes/${connectionId}/${sandboxId}/history/events/${selectedEventId}`,
      ),
    enabled: !!selectedEventId,
    // Cache event detail for 2 minutes — the backend caches output in
    // the projection after first fetch, so subsequent views are fast
    // even after the cache expires.
    staleTime: 120_000,
    gcTime: 300_000,
  });

  const items = data?.items ?? [];

  return (
    <div className="flex h-full flex-col">
      {/* Coverage Badge */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-green-600" />
          <span className="text-sm font-medium">
            {data?.coverage ?? 'Loading…'}
          </span>
          <span className="text-xs text-muted-foreground">
            ({data?.source ?? '—'})
          </span>
        </div>
        <div className="flex items-center gap-3">
          {data?.last_synced_at && (
            <span className="text-xs text-muted-foreground">
              Last sync: {new Date(data.last_synced_at).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => syncMutation.mutate()}
            disabled={isFetching || syncMutation.isPending}
            className="btn-outline btn-sm"
          >
            <RefreshCw className={cn('h-3 w-3', isFetching && 'animate-spin')} />
            Sync
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 border-b px-4 py-2">
        <select
          className="input h-8 w-36 text-xs"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">All Types</option>
          <option value="command">Command</option>
          <option value="file_write">File Write</option>
          <option value="file_read">File Read</option>
          <option value="file_delete">File Delete</option>
          <option value="sandbox.create">Sandbox Create</option>
          <option value="sandbox.delete">Sandbox Delete</option>
        </select>
        <select
          className="input h-8 w-32 text-xs"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
        >
          <option value="">All Status</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
        </select>
        <select
          className="input h-8 w-32 text-xs"
          value={filterSource}
          onChange={(e) => setFilterSource(e.target.value)}
        >
          <option value="">All Sources</option>
          <option value="console">Console</option>
          <option value="sdk">SDK/Agent</option>
          <option value="provider">Provider</option>
        </select>
        <input
          className="input h-8 w-40 text-xs"
          placeholder="Filter by actor ID…"
          value={filterActor}
          onChange={(e) => setFilterActor(e.target.value)}
        />
      </div>

      {/* Main content: list + detail panel side by side */}
      <div className="flex flex-1 overflow-hidden">
        {/* History list */}
        <div className={cn(
          'overflow-auto transition-all',
          selectedEventId ? 'w-1/2 border-r' : 'w-full',
        )}>
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading history…</div>
          ) : items.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              No history events found.
            </div>
          ) : (
            <div className="divide-y">
              {items.map((item, idx) => {
                const Icon = operationIcons[item.operation_type] ?? Terminal;
                const SourceIcon = sourceIcons[item.source] ?? User;
                const isSelected = selectedEventId === item.event_id;
                return (
                  <button
                    key={`${item.event_id}-${idx}`}
                    onClick={() => setSelectedEventId(item.event_id)}
                    className={cn(
                      'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/50',
                      isSelected && 'bg-accent',
                    )}
                  >
                    {/* Icon */}
                    <div className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border',
                      statusColors[item.status] ?? statusColors.succeeded,
                    )}>
                      <Icon className="h-4 w-4" />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0 space-y-1">
                      {/* Row 1: operation type + status + source */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">{item.operation_type}</span>
                        <span className={cn(
                          'rounded border px-1.5 py-0.5 text-xs font-medium',
                          statusColors[item.status] ?? '',
                        )}>
                          {item.status}
                        </span>
                        <span className="flex items-center gap-0.5 text-xs text-muted-foreground">
                          <SourceIcon className="h-3 w-3" />
                          {sourceLabels[item.source] ?? item.source}
                        </span>
                        {item.actor_id && (
                          <span className={cn(
                            'flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-medium',
                            item.actor_type === 'agent'
                              ? 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300'
                              : 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
                          )}>
                            <Bot className="h-3 w-3" />
                            {item.actor_id}
                          </span>
                        )}
                      </div>

                      {/* Row 2: command or file path */}
                      {item.command && (
                        <div className="font-mono text-xs text-muted-foreground truncate">
                          <span className="text-foreground/70">$</span> {item.command}
                        </div>
                      )}
                      {item.file_path && (
                        <div className="font-mono text-xs text-muted-foreground truncate">
                          {item.file_change_type && (
                            <span className="mr-1 rounded bg-muted px-1">{item.file_change_type}</span>
                          )}
                          {item.file_path}
                        </div>
                      )}

                      {/* Row 3: meta info */}
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="flex items-center gap-0.5">
                          <Clock className="h-3 w-3" />
                          {formatTime(item.occurred_at)}
                        </span>
                        {item.duration_ms != null && (
                          <span>{formatDuration(item.duration_ms)}</span>
                        )}
                        {item.exit_code != null && (
                          <span className={item.exit_code === 0 ? 'text-green-600' : 'text-red-600'}>
                            exit: {item.exit_code}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Expand indicator */}
                    <ChevronRight className={cn(
                      'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
                      isSelected && 'rotate-90',
                    )} />
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Detail Panel */}
        {selectedEventId && (
          <div className="w-1/2 overflow-auto">
            {eventDetail ? (
              <EventDetailPanel
                detail={eventDetail}
                onClose={() => setSelectedEventId(null)}
              />
            ) : (
              <div className="p-8 text-center text-muted-foreground">Loading detail…</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}


function EventDetailPanel({
  detail,
  onClose,
}: {
  detail: HistoryEventDetail;
  onClose: () => void;
}) {
  const e = detail.event;

  const isFileOp = !!e.file_path;
  const isCommandOp = !!e.command;

  // Check if there's meaningful diff/content to show for file ops.
  const diff = detail.result?.diff ?? detail.request?.diff;
  const diffTruncated = Boolean(detail.result?.diff_truncated ?? detail.request?.diff_truncated);
  const writtenContent = detail.result?.content ?? detail.request?.content;
  const contentTruncated = Boolean(detail.result?.content_truncated ?? detail.request?.content_truncated);
  const hasDiffOrContent = diff || writtenContent;

  // For commands, check if there's output.
  const hasOutput = detail.stdout || detail.stderr;

  return (
    <div className="flex h-full flex-col">
      {/* Compact header bar */}
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold">{e.operation_type}</span>
          <span className={cn(
            'rounded border px-1.5 py-0.5 text-xs font-medium',
            statusColors[e.status] ?? '',
          )}>
            {e.status}
          </span>
          <span className="flex items-center gap-0.5 text-xs text-muted-foreground">
            {(() => {
              const SourceIcon = sourceIcons[e.source] ?? User;
              return <SourceIcon className="h-3 w-3" />;
            })()}
            {sourceLabels[e.source] ?? e.source}
          </span>
          {e.actor_id && (
            <span className={cn(
              'flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-medium',
              e.actor_type === 'agent'
                ? 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300'
                : 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
            )}>
              <Bot className="h-3 w-3" />
              {e.actor_id}
            </span>
          )}
          <span className="text-xs text-muted-foreground">{formatTime(e.occurred_at)}</span>
          {e.duration_ms != null && (
            <span className="text-xs text-muted-foreground">{formatDuration(e.duration_ms)}</span>
          )}
          {e.exit_code != null && (
            <span className={cn('text-xs', e.exit_code === 0 ? 'text-green-600' : 'text-red-600')}>
              exit: {e.exit_code}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Scrollable content area */}
      <div className="flex-1 overflow-auto p-4">
        {/* File path banner — prominent, shown for file operations */}
        {isFileOp && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2">
            <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
            <code className="font-mono text-sm font-medium">{e.file_path}</code>
            {e.file_change_type && (
              <span className="ml-auto rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {e.file_change_type}
              </span>
            )}
          </div>
        )}

        {/* Command — shown for command operations */}
        {isCommandOp && (
          <div className="mb-4">
            <pre className="overflow-auto rounded bg-muted p-3 font-mono text-xs">
              <span className="text-foreground/70">$ </span>
              {e.command}
            </pre>
            {e.cwd && (
              <div className="mt-1 text-xs text-muted-foreground">
                cwd: <code className="font-mono">{e.cwd}</code>
              </div>
            )}
          </div>
        )}

        {/* Diff or written content for file operations */}
        {isFileOp && Boolean(diff) && (
          <div>
            {diffTruncated && (
              <div className="mb-1 text-xs text-amber-600">
                Diff truncated (64KB limit)
              </div>
            )}
            <DiffViewer diff={String(diff)} />
          </div>
        )}

        {isFileOp && !diff && Boolean(writtenContent) && (
          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Written Content
            </div>
            {contentTruncated && (
              <div className="mb-1 text-xs text-amber-600">
                Content truncated (10KB limit)
              </div>
            )}
            <pre className="overflow-auto rounded bg-gray-50 p-3 font-mono text-xs dark:bg-gray-900">
              {String(writtenContent)}
            </pre>
          </div>
        )}

        {/* New file with no content preview */}
        {isFileOp && !hasDiffOrContent && !Boolean(diff) && !Boolean(writtenContent) && (
          <div className="py-4 text-center text-sm text-muted-foreground">
            No content changes recorded.
          </div>
        )}

        {/* stdout for command operations */}
        {isCommandOp && detail.stdout && (
          <div className="mb-4">
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              stdout
            </div>
            {Boolean(detail.result?.output_truncated) && (
              <div className="mb-1 text-xs text-amber-600">Output truncated (10KB limit per stream)</div>
            )}
            <pre className="max-h-[40vh] overflow-auto rounded bg-gray-50 p-3 font-mono text-xs dark:bg-gray-900">
              {detail.stdout}
            </pre>
          </div>
        )}

        {/* stderr for command operations */}
        {isCommandOp && detail.stderr && (
          <div className="mb-4">
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              stderr
            </div>
            {Boolean(detail.result?.output_truncated) && !detail.stdout && (
              <div className="mb-1 text-xs text-amber-600">Output truncated (10KB limit per stream)</div>
            )}
            <pre className="max-h-[40vh] overflow-auto rounded bg-red-50 p-3 font-mono text-xs text-red-900 dark:bg-red-950">
              {detail.stderr}
            </pre>
          </div>
        )}

        {/* No output for commands */}
        {isCommandOp && !hasOutput && (
          <div className="py-4 text-center text-sm text-muted-foreground">
            No output captured.
          </div>
        )}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// DiffViewer — parses unified diff text and renders a Git-style view with
// line numbers, colored backgrounds for additions/deletions, and hunk
// headers.
// ---------------------------------------------------------------------------

type DiffLineType = 'context' | 'add' | 'remove' | 'meta';

interface DiffLine {
  type: DiffLineType;
  content: string;
  oldLine: number | null;
  newLine: number | null;
}

function parseUnifiedDiff(diff: string): DiffLine[] {
  const lines = diff.split('\n');
  const result: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // File headers: --- / +++ — skip these, the file path is already
    // shown in the panel header above the diff.
    if (line.startsWith('--- ') || line.startsWith('+++ ')) {
      continue;
    }

    // Hunk header: @@ -A,B +C,D @@ — parse line numbers but skip
    // rendering the header itself (it adds visual noise without value).
    const hunkMatch = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunkMatch) {
      oldLine = parseInt(hunkMatch[1], 10);
      newLine = parseInt(hunkMatch[2], 10);
      continue;
    }

    // No-newline marker
    if (line.startsWith('\\')) {
      result.push({ type: 'meta', content: line, oldLine: null, newLine: null });
      continue;
    }

    // Addition
    if (line.startsWith('+')) {
      result.push({
        type: 'add',
        content: line.slice(1),
        oldLine: null,
        newLine: newLine++,
      });
      continue;
    }

    // Deletion
    if (line.startsWith('-')) {
      result.push({
        type: 'remove',
        content: line.slice(1),
        oldLine: oldLine++,
        newLine: null,
      });
      continue;
    }

    // Context line (starts with space or is empty)
    const content = line.startsWith(' ') ? line.slice(1) : line;
    result.push({
      type: 'context',
      content,
      oldLine: oldLine++,
      newLine: newLine++,
    });
  }

  return result;
}

const lineTypeStyles: Record<DiffLineType, { bg: string; prefix: string; text: string }> = {
  context: { bg: '', prefix: 'text-muted-foreground/40', text: 'text-foreground/80' },
  add: { bg: 'bg-green-50 dark:bg-green-950/40', prefix: 'text-green-600 dark:text-green-400', text: 'text-green-900 dark:text-green-100' },
  remove: { bg: 'bg-red-50 dark:bg-red-950/40', prefix: 'text-red-600 dark:text-red-400', text: 'text-red-900 dark:text-red-100' },
  meta: { bg: '', prefix: 'text-muted-foreground/50', text: 'text-muted-foreground italic' },
};

function DiffViewer({ diff }: { diff: string }) {
  const lines = useMemo(() => parseUnifiedDiff(diff), [diff]);

  // Compute stats
  const stats = useMemo(() => {
    let added = 0;
    let removed = 0;
    for (const l of lines) {
      if (l.type === 'add') added++;
      else if (l.type === 'remove') removed++;
    }
    return { added, removed };
  }, [lines]);

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      {/* Stats bar */}
      <div className="flex items-center gap-3 border-b bg-muted/30 px-3 py-1.5 text-xs">
        <span className="font-mono">
          <span className="text-green-600 dark:text-green-400">+{stats.added}</span>
          {' '}
          <span className="text-red-600 dark:text-red-400">-{stats.removed}</span>
        </span>
        <span className="text-muted-foreground">
          {stats.added + stats.removed} lines changed
        </span>
      </div>

      {/* Diff body */}
      <div className="max-h-[28rem] overflow-auto font-mono text-xs">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, idx) => {
              const style = lineTypeStyles[line.type];
              const prefix =
                line.type === 'add' ? '+' :
                line.type === 'remove' ? '-' :
                '';
              return (
                <tr key={idx} className={cn('border-b border-border/30', style.bg)}>
                  {/* Old line number */}
                  <td className="w-12 select-none whitespace-nowrap border-r border-border/30 px-2 py-0 text-right align-top text-muted-foreground/50">
                    {line.oldLine ?? ''}
                  </td>
                  {/* New line number */}
                  <td className="w-12 select-none whitespace-nowrap border-r border-border/30 px-2 py-0 text-right align-top text-muted-foreground/50">
                    {line.newLine ?? ''}
                  </td>
                  {/* +/- prefix */}
                  <td className={cn('w-4 select-none px-1 py-0 text-center align-top', style.prefix)}>
                    {prefix}
                  </td>
                  {/* Content */}
                  <td className={cn('whitespace-pre-wrap break-all px-2 py-0 leading-5', style.text)}>
                    {line.content || '\u00A0'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
