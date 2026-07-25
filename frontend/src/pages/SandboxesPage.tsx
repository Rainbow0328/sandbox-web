import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Boxes, RefreshCw, Search, ExternalLink, Plus, X, AlertCircle, Link2, Globe, Clock } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { api, type SandboxListResponse, type ConnectionResponse } from '@/lib/api';
import { cn } from '@/lib/utils';

const stateColors: Record<string, string> = {
  running: 'border-green-300 bg-green-100 text-green-700',
  paused: 'border-yellow-300 bg-yellow-100 text-yellow-700',
  stopped: 'border-gray-300 bg-gray-100 text-gray-700',
  failed: 'border-red-300 bg-red-100 text-red-700',
  creating: 'border-blue-300 bg-blue-100 text-blue-700',
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
    });
  } catch {
    return iso;
  }
}

function timeAgo(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    if (diff < 60_000) return 'just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
  } catch {
    return iso;
  }
}

export function SandboxesPage() {
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const queryClient = useQueryClient();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['sandboxes'],
    queryFn: () => api.get<SandboxListResponse>('/sandboxes'),
    refetchInterval: 30_000,
  });

  // Lazy-load connections only when the Create dialog is open.
  const { data: connections = [] } = useQuery({
    queryKey: ['connections'],
    queryFn: () => api.get<ConnectionResponse[]>('/connections'),
    enabled: showCreate,
    staleTime: 60_000,
  });

  const navigate = useNavigate();

  const createMutation = useMutation({
    mutationFn: (data: { connectionId: string; image: string; workdir: string; name: string; ttlSeconds?: number }) =>
      api.post<{ sandbox_id: string; connection_id: string }>(`/connections/${data.connectionId}/sandboxes`, {
        image: data.image,
        workdir: data.workdir,
        name: data.name,
        ttl_seconds: data.ttlSeconds ?? null,
      }),
    onSuccess: (result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sandboxes'] });
      setShowCreate(false);
      // Navigate to sandbox detail in the same tab.
      navigate(`/sandboxes/${variables.connectionId}/${result.sandbox_id}?tab=overview`);
    },
  });

  const createDirectMutation = useMutation({
    mutationFn: (data: { endpoint: string; apiKey: string; image: string; workdir: string; name: string; ttlSeconds?: number }) =>
      api.post<{ sandbox_id: string; connection_id: string }>(`/sandboxes`, {
        endpoint: data.endpoint,
        api_key: data.apiKey,
        image: data.image,
        workdir: data.workdir,
        name: data.name,
        ttl_seconds: data.ttlSeconds ?? null,
        save_connection: true,
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['sandboxes'] });
      queryClient.invalidateQueries({ queryKey: ['connections'] });
      setShowCreate(false);
      navigate(`/sandboxes/${result.connection_id}/${result.sandbox_id}?tab=overview`);
    },
  });

  const sandboxes = data?.items ?? [];
  const filtered = sandboxes.filter((s) => {
    if (stateFilter && s.state !== stateFilter) return false;
    const q = search.toLowerCase();
    if (search && !s.sandbox_id.toLowerCase().includes(q) && !(s.name ?? '').toLowerCase().includes(q)) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Boxes className="h-5 w-5" />
          <h1 className="text-xl font-semibold">Sandboxes</h1>
          {data && (
            <span className="text-sm text-muted-foreground">({data.total} total)</span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary"
          >
            <Plus className="h-4 w-4" />
            Create Sandbox
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="btn-outline"
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            className="input pl-9"
            placeholder="Search by name or ID…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="input w-40"
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
        >
          <option value="">All states</option>
          <option value="running">Running</option>
          <option value="paused">Paused</option>
          <option value="stopped">Stopped</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-muted-foreground">Loading sandboxes…</div>
      ) : filtered.length === 0 ? (
        <div className="rounded-md border border-dashed p-12 text-center text-muted-foreground">
          {sandboxes.length === 0 ? (
            <>
              No sandboxes yet. Click <strong>Create Sandbox</strong> to create one.
            </>
          ) : (
            'No sandboxes match the current filters.'
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Name</th>
                <th className="px-4 py-2 text-left font-medium">Sandbox ID</th>
                <th className="px-4 py-2 text-left font-medium">State</th>
                <th className="px-4 py-2 text-left font-medium">Image</th>
                <th className="px-4 py-2 text-left font-medium">Created</th>
                <th className="px-4 py-2 text-left font-medium">Last Activity</th>
                <th className="px-4 py-2 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filtered.map((s) => (
                <tr key={`${s.connection_id}-${s.sandbox_id}`} className="hover:bg-accent/50">
                  <td className="px-4 py-2 font-medium">
                    {s.name || <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{s.sandbox_id}</td>
                  <td className="px-4 py-2">
                    <span className={cn('badge', stateColors[s.state] ?? stateColors.stopped)}>
                      {s.state}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">{s.image ?? '—'}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground whitespace-nowrap">
                    {formatDateTime(s.created_at)}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground whitespace-nowrap">
                    {s.last_activity_at ? (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {timeAgo(s.last_activity_at)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <Link
                      to={`/sandboxes/${s.connection_id}/${s.sandbox_id}?tab=overview`}
                      className="btn-outline btn-sm"
                    >
                      <ExternalLink className="h-3 w-3" /> Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateSandboxForm
          connections={connections}
          isCreating={createMutation.isPending || createDirectMutation.isPending}
          error={
            createMutation.error instanceof Error
              ? createMutation.error.message
              : createDirectMutation.error instanceof Error
                ? createDirectMutation.error.message
                : null
          }
          onSubmit={(data) => createMutation.mutate(data)}
          onDirectSubmit={(data) => createDirectMutation.mutate(data)}
          onCancel={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}

function CreateSandboxForm({
  connections,
  isCreating,
  error,
  onSubmit,
  onDirectSubmit,
  onCancel,
}: {
  connections: ConnectionResponse[];
  isCreating: boolean;
  error: string | null;
  onSubmit: (data: { connectionId: string; image: string; workdir: string; name: string; ttlSeconds?: number }) => void;
  onDirectSubmit: (data: { endpoint: string; apiKey: string; image: string; workdir: string; name: string; ttlSeconds?: number }) => void;
  onCancel: () => void;
}) {
  const [mode, setMode] = useState<'connection' | 'direct'>(connections.length > 0 ? 'connection' : 'direct');
  const [connectionId, setConnectionId] = useState(connections[0]?.id ?? '');
  const [name, setName] = useState('');
  const [image, setImage] = useState('python:3.12');
  const [workdir, setWorkdir] = useState('/');
  const [ttlSeconds, setTtlSeconds] = useState('');
  // Direct mode fields
  const [endpoint, setEndpoint] = useState('');
  const [apiKey, setApiKey] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const autoName = name || `${image.split(':')[0]}-${Date.now().toString(36).slice(-4)}`;
    if (mode === 'connection') {
      onSubmit({
        connectionId,
        image,
        workdir,
        name: autoName,
        ttlSeconds: ttlSeconds ? parseInt(ttlSeconds, 10) : undefined,
      });
    } else {
      onDirectSubmit({
        endpoint,
        apiKey,
        image,
        workdir,
        name: autoName,
        ttlSeconds: ttlSeconds ? parseInt(ttlSeconds, 10) : undefined,
      });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Create Sandbox</h2>
          <button onClick={onCancel} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Mode toggle */}
        <div className="mb-4 flex gap-2">
          <button
            type="button"
            onClick={() => setMode('connection')}
            className={cn(
              'flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors',
              mode === 'connection'
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background hover:bg-accent',
            )}
          >
            <Link2 className="h-3.5 w-3.5" />
            From Connection
          </button>
          <button
            type="button"
            onClick={() => setMode('direct')}
            className={cn(
              'flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors',
              mode === 'direct'
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background hover:bg-accent',
            )}
          >
            <Globe className="h-3.5 w-3.5" />
            Direct (URL + API Key)
          </button>
        </div>

        {error && (
          <div className="mb-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'connection' ? (
            <div>
              <label className="mb-1 block text-sm font-medium">Connection</label>
              <select
                className="input"
                value={connectionId}
                onChange={(e) => setConnectionId(e.target.value)}
                required
              >
                {connections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.provider_type})
                  </option>
                ))}
              </select>
              {connections.length === 0 && (
                <p className="mt-1 text-xs text-muted-foreground">
                  No connections available. Switch to "Direct" mode or{' '}
                  <Link to="/connections" className="text-primary underline">
                    register a connection
                  </Link>
                  .
                </p>
              )}
            </div>
          ) : (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium">Endpoint URL</label>
                <input
                  className="input"
                  value={endpoint}
                  onChange={(e) => setEndpoint(e.target.value)}
                  placeholder="https://your-sandbox-server.com"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">API Key</label>
                <input
                  className="input"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  A connection will be auto-created for future reuse.
                </p>
              </div>
            </>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium">Sandbox Name</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. dev-env-1 (auto-generated if empty)"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Image</label>
            <input
              className="input"
              value={image}
              onChange={(e) => setImage(e.target.value)}
              placeholder="python:3.12"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Working Directory</label>
            <input
              className="input"
              value={workdir}
              onChange={(e) => setWorkdir(e.target.value)}
              placeholder="/"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">TTL (seconds, optional)</label>
            <input
              className="input"
              type="number"
              value={ttlSeconds}
              onChange={(e) => setTtlSeconds(e.target.value)}
              placeholder="Leave empty for server default"
              min={60}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Sandbox auto-deletes after this duration. Leave empty to use server default.
            </p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onCancel} className="btn-outline">
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={isCreating}>
              {isCreating ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
