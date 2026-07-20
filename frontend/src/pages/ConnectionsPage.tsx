import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Server, Plus, Trash2, Zap, X } from 'lucide-react';
import { api, type ConnectionResponse, type ConnectionTestResult } from '@/lib/api';
import { cn } from '@/lib/utils';

export function ConnectionsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, ConnectionTestResult>>({});

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['connections'],
    queryFn: () => api.get<ConnectionResponse[]>('/connections'),
  });

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      provider_type: string;
      endpoint: string;
      auth_method: string;
      credentials: Record<string, unknown>;
    }) => api.post<ConnectionResponse>('/connections', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connections'] });
      setShowForm(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/connections/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connections'] });
    },
  });

  const testMutation = useMutation({
    mutationFn: (id: string) => api.post<ConnectionTestResult>(`/connections/${id}/test`),
    onSuccess: (result, id) => {
      setTestResults((prev) => ({ ...prev, [id]: result }));
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server className="h-5 w-5" />
          <h1 className="text-xl font-semibold">Connections</h1>
        </div>
        <button onClick={() => setShowForm(true)} className="btn-primary">
          <Plus className="h-4 w-4" />
          Add Connection
        </button>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading connections…</div>
      ) : connections.length === 0 ? (
        <div className="rounded-md border border-dashed p-12 text-center text-muted-foreground">
          No connections registered. Click "Add Connection" to get started.
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Name</th>
                <th className="px-4 py-2 text-left font-medium">Type</th>
                <th className="px-4 py-2 text-left font-medium">Endpoint</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
                <th className="px-4 py-2 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {connections.map((c) => {
                const test = testResults[c.id];
                return (
                  <tr key={c.id} className="hover:bg-accent/50">
                    <td className="px-4 py-2 font-medium">{c.name}</td>
                    <td className="px-4 py-2 text-muted-foreground">{c.provider_type}</td>
                    <td className="px-4 py-2 text-muted-foreground">{c.endpoint}</td>
                    <td className="px-4 py-2">
                      {c.enabled ? (
                        <span className="badge border-green-300 bg-green-100 text-green-700">Enabled</span>
                      ) : (
                        <span className="badge border-red-300 bg-red-100 text-red-700">Disabled</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-2">
                        <button
                          onClick={() => testMutation.mutate(c.id)}
                          disabled={testMutation.isPending}
                          className="btn-outline btn-sm"
                        >
                          <Zap className="h-3 w-3" />
                          Test
                        </button>
                        <button
                          onClick={() => deleteMutation.mutate(c.id)}
                          className="btn-outline btn-sm text-destructive"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                      {test && (
                        <div
                          className={cn(
                            'mt-1 text-xs',
                            test.ok ? 'text-green-600' : 'text-destructive',
                          )}
                        >
                          {test.ok ? '✓ Connected' : `✗ ${test.message}`}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showForm && <CreateConnectionForm onSubmit={(d) => createMutation.mutate(d)} onCancel={() => setShowForm(false)} />}
    </div>
  );
}

function CreateConnectionForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (data: {
    name: string;
    provider_type: string;
    endpoint: string;
    auth_method: string;
    credentials: Record<string, unknown>;
  }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState('');
  const [providerType, setProviderType] = useState('opensandbox');
  const [endpoint, setEndpoint] = useState('');
  const [authMethod, setAuthMethod] = useState('api_key');
  const [apiKey, setApiKey] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      provider_type: providerType,
      endpoint,
      auth_method: authMethod,
      credentials: { api_key: apiKey },
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Add Connection</h2>
          <button onClick={onCancel} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Provider Type</label>
            <select className="input" value={providerType} onChange={(e) => setProviderType(e.target.value)}>
              <option value="opensandbox">opensandbox</option>
              <option value="fake">fake (dev only)</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Endpoint</label>
            <input className="input" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Auth Method</label>
            <select className="input" value={authMethod} onChange={(e) => setAuthMethod(e.target.value)}>
              <option value="api_key">API Key</option>
              <option value="basic">Basic</option>
              <option value="bearer">Bearer</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">API Key</label>
            <input
              className="input"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Connection API key"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onCancel} className="btn-outline">
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
