import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Boxes,
  Server,
  Shield,
  Users,
  Activity,
  Cpu,
  FileText,
  Terminal,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  TrendingUp,
  Zap,
  AlertCircle,
} from 'lucide-react';
import { api, type DashboardOverview } from '@/lib/api';
import { cn } from '@/lib/utils';

const stateColors: Record<string, string> = {
  running: 'border-green-300 bg-green-100 text-green-700',
  paused: 'border-yellow-300 bg-yellow-100 text-yellow-700',
  stopped: 'border-gray-300 bg-gray-100 text-gray-700',
  failed: 'border-red-300 bg-red-100 text-red-700',
  creating: 'border-blue-300 bg-blue-100 text-blue-700',
};

const statusColors: Record<string, string> = {
  succeeded: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  running: 'bg-blue-100 text-blue-700',
  cancelled: 'bg-gray-100 text-gray-600',
  timed_out: 'bg-yellow-100 text-yellow-700',
};

const sourceColors: Record<string, string> = {
  console: 'bg-purple-100 text-purple-700',
  sdk: 'bg-indigo-100 text-indigo-700',
  provider: 'bg-cyan-100 text-cyan-700',
  gateway: 'bg-orange-100 text-orange-700',
};

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
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
  if (ms === null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}min`;
}

// ─── Stat Card ────────────────────────────────────────────────────────
interface StatCardProps {
  icon: typeof Boxes;
  label: string;
  value: number;
  subtext?: string;
  onClick?: () => void;
  accent?: string;
}

function StatCard({ icon: Icon, label, value, subtext, onClick, accent }: StatCardProps) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        'flex flex-col gap-2 rounded-xl border bg-card p-4 text-left shadow-sm transition-all',
        onClick
          ? 'cursor-pointer hover:shadow-md hover:border-primary/40'
          : 'cursor-default',
        accent === 'green' && 'border-l-4 border-l-green-400',
        accent === 'blue' && 'border-l-4 border-l-blue-400',
        accent === 'purple' && 'border-l-4 border-l-purple-400',
        accent === 'orange' && 'border-l-4 border-l-orange-400',
        accent === 'cyan' && 'border-l-4 border-l-cyan-400',
        !accent && 'border-l-4 border-l-gray-300',
      )}
    >
      <div className="flex items-center justify-between">
        <Icon className="h-5 w-5 text-muted-foreground" />
        <span className="text-3xl font-bold">{value}</span>
      </div>
      <div>
        <p className="text-sm font-medium">{label}</p>
        {subtext && <p className="text-xs text-muted-foreground">{subtext}</p>}
      </div>
    </button>
  );
}

// ─── State Badge ──────────────────────────────────────────────────────
function StateBadge({ state }: { state: string }) {
  return (
    <span className={cn('rounded-md border px-1.5 py-0.5 text-xs font-medium', stateColors[state] ?? 'border-gray-300 bg-gray-100 text-gray-600')}>
      {state}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', statusColors[status] ?? 'bg-gray-100 text-gray-600')}>
      {status}
    </span>
  );
}

function SourceBadge({ source }: { source: string }) {
  return (
    <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', sourceColors[source] ?? 'bg-gray-100 text-gray-600')}>
      {source}
    </span>
  );
}

// ─── Bar Chart (horizontal) ───────────────────────────────────────────
function MiniBarChart({ data, colorMap }: { data: Record<string, number>; colorMap?: Record<string, string> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, v]) => sum + v, 0) || 1;

  return (
    <div className="flex flex-col gap-2">
      {entries.length === 0 && <span className="text-xs text-muted-foreground">No data</span>}
      {entries.map(([key, val]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="w-24 truncate text-xs text-muted-foreground">{key}</span>
          <div className="relative h-6 flex-1 rounded bg-secondary overflow-hidden">
            <div
              className={cn('absolute left-0 top-0 h-full rounded', colorMap?.[key] ?? 'bg-primary')}
              style={{ width: `${(val / total) * 100}%` }}
            />
            <span className="absolute left-1.5 top-1/2 -translate-y-1/2 text-xs font-medium leading-none">{val}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────
export function DashboardPage() {
  const navigate = useNavigate();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: () => api.get<DashboardOverview>('/dashboard/overview'),
    refetchInterval: 15_000,
  });

  if (isLoading || !data) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading dashboard...
        </div>
      </div>
    );
  }

  const opTypeColors: Record<string, string> = {
    command: 'bg-blue-400',
    file_write: 'bg-green-400',
    file_read: 'bg-cyan-400',
    terminal: 'bg-purple-400',
    file_delete: 'bg-red-400',
    backup: 'bg-orange-400',
  };

  const opStatusColors: Record<string, string> = {
    succeeded: 'bg-green-400',
    failed: 'bg-red-400',
    running: 'bg-blue-400',
    cancelled: 'bg-gray-400',
    timed_out: 'bg-yellow-400',
  };

  const opSourceColors: Record<string, string> = {
    console: 'bg-purple-400',
    sdk: 'bg-indigo-400',
    provider: 'bg-cyan-400',
    gateway: 'bg-orange-400',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Sandbox & Agent operations overview</p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* Top Stat Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard
          icon={Server}
          label="Connections"
          value={data.connections.total}
          subtext={`${data.connections.enabled} enabled`}
          accent="blue"
          onClick={() => navigate('/connections')}
        />
        <StatCard
          icon={Boxes}
          label="Sandboxes"
          value={data.sandboxes.total}
          subtext={`${data.workspaces.active} reusable`}
          accent="green"
          onClick={() => navigate('/sandboxes')}
        />
        <StatCard
          icon={Users}
          label="Agents"
          value={data.agents.total}
          subtext={`${data.agents.online} online`}
          accent="purple"
          onClick={() => navigate('/policies')}
        />
        <StatCard
          icon={Shield}
          label="Policy Rules"
          value={data.policy_rules.total}
          subtext={`${data.policy_rules.allow} allow / ${data.policy_rules.deny} deny`}
          accent="orange"
          onClick={() => navigate('/policies')}
        />
        <StatCard
          icon={Activity}
          label="Operations"
          value={data.operations.total}
          subtext="total events"
          accent="cyan"
        />
        <StatCard
          icon={Cpu}
          label="Groups"
          value={data.policy_groups.total}
          subtext={`${data.policy_groups.enabled} enabled`}
          accent="blue"
          onClick={() => navigate('/policies')}
        />
      </div>

      {/* Sandbox State Breakdown + Sandbox List */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* State breakdown */}
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
            <Boxes className="h-4 w-4" />
            Sandbox State Breakdown
          </h2>
          {Object.keys(data.sandboxes.by_state).length === 0 ? (
            <p className="text-xs text-muted-foreground">No sandboxes found</p>
          ) : (
            <div className="flex flex-col gap-2">
              {Object.entries(data.sandboxes.by_state).map(([state, count]) => (
                <div key={state} className="flex items-center gap-2">
                  <StateBadge state={state} />
                  <div className="relative h-6 flex-1 rounded bg-secondary overflow-hidden">
                    <div
                      className="absolute left-0 top-0 h-full rounded bg-primary"
                      style={{ width: `${(count / data.sandboxes.total) * 100}%` }}
                    />
                    <span className="absolute left-1.5 top-1/2 -translate-y-1/2 text-xs font-medium leading-none">{count}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Sandbox list */}
        <div className="lg:col-span-2 rounded-xl border bg-card p-4 shadow-sm">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
            <Terminal className="h-4 w-4" />
            Active Sandboxes
            <button
              onClick={() => navigate('/sandboxes')}
              className="ml-auto text-xs text-primary hover:underline"
            >
              View all →
            </button>
          </h2>
          {data.sandbox_summaries.length === 0 ? (
            <p className="text-xs text-muted-foreground">No sandboxes found</p>
          ) : (
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="px-2 py-1 text-left font-medium">Name</th>
                    <th className="px-2 py-1 text-left font-medium">State</th>
                    <th className="px-2 py-1 text-left font-medium">Last Activity</th>
                    <th className="px-2 py-1 text-left font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sandbox_summaries.slice(0, 15).map((sb) => (
                    <tr
                      key={`${sb.connection_id}-${sb.sandbox_id}`}
                      className="border-b hover:bg-accent cursor-pointer"
                      onClick={() => {
                        if (sb.connection_id) {
                          navigate(`/sandboxes/${sb.connection_id}/${sb.sandbox_id}`);
                        }
                      }}
                    >
                      <td className="px-2 py-1.5 truncate max-w-32 font-mono text-xs">
                        {sb.name || sb.sandbox_id}
                      </td>
                      <td className="px-2 py-1.5">
                        <StateBadge state={sb.state} />
                      </td>
                      <td className="px-2 py-1.5 text-xs text-muted-foreground">
                        {formatDateTime(sb.last_activity_at)}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-muted-foreground">
                        {formatDateTime(sb.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Operation Statistics */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* By Type */}
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
            <Zap className="h-4 w-4" />
            Operations by Type
          </h2>
          <MiniBarChart data={data.operations.by_type} colorMap={opTypeColors} />
        </div>

        {/* By Status */}
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
            <CheckCircle2 className="h-4 w-4" />
            Operations by Status
          </h2>
          <MiniBarChart data={data.operations.by_status} colorMap={opStatusColors} />
        </div>

        {/* By Source */}
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
            <Server className="h-4 w-4" />
            Operations by Source
          </h2>
          <MiniBarChart data={data.operations.by_source} colorMap={opSourceColors} />
        </div>
      </div>

      {/* Top Actors + Recent Operations */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Top Actors */}
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
            <TrendingUp className="h-4 w-4" />
            Top Actors (by Operations)
          </h2>
          {data.operations.by_actor.length === 0 ? (
            <p className="text-xs text-muted-foreground">No actor data</p>
          ) : (
            <div className="space-y-2">
              {data.operations.by_actor.map((actor) => {
                const maxCount = data.operations.by_actor[0]?.count || 1;
                return (
                  <div key={actor.actor_id} className="flex items-center gap-2">
                    <span className="w-32 truncate text-xs font-mono text-muted-foreground">
                      {actor.actor_id}
                    </span>
                    <div className="relative h-5 flex-1 rounded bg-secondary overflow-hidden">
                      <div
                        className="absolute left-0 top-0 h-full rounded bg-primary"
                        style={{ width: `${(actor.count / maxCount) * 100}%` }}
                      />
                      <span className="absolute left-1.5 top-1/2 -translate-y-1/2 text-xs font-medium leading-none">{actor.count}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Recent Operations */}
        <div className="lg:col-span-2 rounded-xl border bg-card p-4 shadow-sm">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold">
            <Clock className="h-4 w-4" />
            Recent Operations
          </h2>
          {data.operations.recent.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <AlertCircle className="h-3 w-3" />
              No recent operations
            </div>
          ) : (
            <div className="max-h-96 overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="px-2 py-1 text-left font-medium">Time</th>
                    <th className="px-2 py-1 text-left font-medium">Type</th>
                    <th className="px-2 py-1 text-left font-medium">Status</th>
                    <th className="px-2 py-1 text-left font-medium">Source</th>
                    <th className="px-2 py-1 text-left font-medium">Actor</th>
                    <th className="px-2 py-1 text-left font-medium">Detail</th>
                    <th className="px-2 py-1 text-left font-medium">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {data.operations.recent.map((op) => (
                    <tr
                      key={op.event_id}
                      className="border-b hover:bg-accent cursor-pointer"
                      onClick={() => {
                        if (op.connection_id) {
                          navigate(`/sandboxes/${op.connection_id}/${op.sandbox_id}?tab=history`);
                        }
                      }}
                    >
                      <td className="px-2 py-1.5 text-xs text-muted-foreground whitespace-nowrap">
                        {formatDateTime(op.occurred_at)}
                      </td>
                      <td className="px-2 py-1.5">
                        <span className="inline-flex items-center gap-1 text-xs">
                          {op.operation_type === 'command' && <Terminal className="h-3 w-3" />}
                          {op.operation_type?.startsWith('file') && <FileText className="h-3 w-3" />}
                          {op.operation_type}
                        </span>
                      </td>
                      <td className="px-2 py-1.5">
                        <StatusBadge status={op.status} />
                      </td>
                      <td className="px-2 py-1.5">
                        <SourceBadge source={op.source} />
                      </td>
                      <td className="px-2 py-1.5 text-xs font-mono text-muted-foreground truncate max-w-20">
                        {op.actor_id ?? '—'}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-muted-foreground truncate max-w-40">
                        {op.command ?? op.file_path ?? '—'}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-muted-foreground whitespace-nowrap">
                        {formatDuration(op.duration_ms)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
