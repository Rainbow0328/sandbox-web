import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  History as HistoryIcon,
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
  ChevronDown,
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
    refetchInterval: 30_000,
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
                          <span className="text-xs text-muted-foreground">
                            · {item.actor_id}
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

  return (
    <div className="p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-semibold">Event Detail</h3>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Meta grid */}
      <div className="mb-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <DetailField label="Event ID" value={e.event_id} mono />
        <DetailField label="Source" value={sourceLabels[e.source] ?? e.source} />
        <DetailField label="Actor" value={`${e.actor_type}: ${e.actor_id ?? '—'}`} />
        <DetailField label="Operation" value={e.operation_type} />
        <DetailField label="Status" value={e.status} />
        <DetailField label="Occurred" value={formatTime(e.occurred_at)} />
        {e.duration_ms != null && (
          <DetailField label="Duration" value={formatDuration(e.duration_ms)} />
        )}
        {e.exit_code != null && (
          <DetailField label="Exit Code" value={String(e.exit_code)} mono />
        )}
        {e.thread_id && <DetailField label="Thread" value={e.thread_id} mono />}
        {e.run_id && <DetailField label="Run ID" value={e.run_id} mono />}
        {e.cwd && <DetailField label="CWD" value={e.cwd} mono />}
      </div>

      {/* Command */}
      {e.command && (
        <Section title="Command">
          <pre className="overflow-auto rounded bg-muted p-3 font-mono text-xs">
            {e.command}
          </pre>
        </Section>
      )}

      {/* File info */}
      {e.file_path && (
        <Section title="File Operation">
          <div className="space-y-1 text-sm">
            <div><span className="text-muted-foreground">Path:</span> <code className="text-xs">{e.file_path}</code></div>
            {e.file_change_type && (
              <div><span className="text-muted-foreground">Change:</span> {e.file_change_type}</div>
            )}
          </div>
        </Section>
      )}

      {/* Request */}
      {detail.request && Object.keys(detail.request).length > 0 && (
        <Section title="Request">
          <pre className="max-h-48 overflow-auto rounded bg-muted p-3 font-mono text-xs">
            {JSON.stringify(detail.request, null, 2)}
          </pre>
        </Section>
      )}

      {/* stdout */}
      {detail.stdout && (
        <Section title="stdout">
          <pre className="max-h-64 overflow-auto rounded bg-gray-50 p-3 font-mono text-xs dark:bg-gray-900">
            {detail.stdout}
          </pre>
        </Section>
      )}

      {/* stderr */}
      {detail.stderr && (
        <Section title="stderr">
          <pre className="max-h-64 overflow-auto rounded bg-red-50 p-3 font-mono text-xs text-red-900 dark:bg-red-950">
            {detail.stderr}
          </pre>
        </Section>
      )}

      {/* Result */}
      {detail.result && Object.keys(detail.result).length > 0 && (
        <Section title="Result">
          <pre className="max-h-48 overflow-auto rounded bg-muted p-3 font-mono text-xs">
            {JSON.stringify(detail.result, null, 2)}
          </pre>
        </Section>
      )}
    </div>
  );
}


function DetailField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('text-sm', mono && 'font-mono text-xs')}>{value}</div>
    </div>
  );
}


function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  );
}
