import { useState } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Pause, Play, Trash2, Folder, Terminal, Info, History, FileArchive, Shield, Plus, AlertCircle, CheckCircle2, Zap, X } from 'lucide-react';
import { api, type SandboxInfo, type Capabilities, type PolicyRule } from '@/lib/api';
import { cn } from '@/lib/utils';
import { FilesTab } from '@/features/sandbox-files/FilesTab';
import { CommandsTab } from '@/features/sandbox-commands/CommandsTab';
import { HistoryTab } from '@/features/sandbox-history/HistoryTab';
import { BackupsTab } from '@/features/sandbox-backups/BackupsTab';

type TabId = 'overview' | 'files' | 'commands' | 'history' | 'backups' | 'policies';

const tabs: { id: TabId; label: string; icon: typeof Info }[] = [
  { id: 'overview', label: '概览', icon: Info },
  { id: 'files', label: '文件', icon: Folder },
  { id: 'commands', label: '命令', icon: Terminal },
  { id: 'history', label: '历史', icon: History },
  { id: 'backups', label: '备份', icon: FileArchive },
  { id: 'policies', label: '权限', icon: Shield },
];

export function SandboxDetailPage() {
  const { connectionId, sandboxId } = useParams<{ connectionId: string; sandboxId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tab = (searchParams.get('tab') as TabId) || 'overview';

  const { data: sandbox } = useQuery({
    queryKey: ['sandbox', connectionId, sandboxId],
    queryFn: () =>
      api.get<SandboxInfo>(`/connections/${connectionId}/sandboxes/${sandboxId}`),
    enabled: !!connectionId && !!sandboxId,
    refetchInterval: 30_000,
  });

  const { data: capabilities } = useQuery({
    queryKey: ['capabilities', connectionId, sandboxId],
    queryFn: () =>
      api.get<Capabilities>(`/connections/${connectionId}/sandboxes/${sandboxId}/capabilities`),
    enabled: !!connectionId && !!sandboxId,
  });

  const pauseMutation = useMutation({
    mutationFn: () => api.post(`/connections/${connectionId}/sandboxes/${sandboxId}/pause`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sandbox', connectionId, sandboxId] }),
  });

  const resumeMutation = useMutation({
    mutationFn: () => api.post(`/connections/${connectionId}/sandboxes/${sandboxId}/resume`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sandbox', connectionId, sandboxId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/connections/${connectionId}/sandboxes/${sandboxId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sandboxes'] });
      navigate('/sandboxes');
    },
  });

  const setTab = (id: TabId) => {
    setSearchParams({ tab: id });
  };

  const stateColors: Record<string, string> = {
    running: 'border-green-300 bg-green-100 text-green-700',
    paused: 'border-yellow-300 bg-yellow-100 text-yellow-700',
    stopped: 'border-gray-300 bg-gray-100 text-gray-700',
  };

  return (
    <div className="flex h-full flex-col">
      {/* SubTopBar */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-3">
          <Link to="/sandboxes" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <span className="font-mono text-sm">{sandboxId}</span>
          {sandbox && (
            <span className={cn('badge', stateColors[sandbox.state] ?? stateColors.stopped)}>
              {sandbox.state}
            </span>
          )}
          {sandbox?.image && (
            <span className="text-sm text-muted-foreground">{sandbox.image}</span>
          )}
        </div>
        <div className="flex gap-2">
          {sandbox?.state === 'running' && (
            <button
              onClick={() => pauseMutation.mutate()}
              disabled={pauseMutation.isPending}
              className="btn-outline btn-sm"
            >
              <Pause className="h-3 w-3" /> Pause
            </button>
          )}
          {sandbox?.state === 'paused' && (
            <button
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending}
              className="btn-outline btn-sm"
            >
              <Play className="h-3 w-3" /> Resume
            </button>
          )}
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
            className="btn-outline btn-sm text-destructive"
          >
            <Trash2 className="h-3 w-3" /> Delete
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b px-4">
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                tab === t.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        {tab === 'overview' && (
          <div className="grid gap-4 p-4 md:grid-cols-2">
            <Card title="基本信息">
              {sandbox ? (
                <dl className="space-y-1 text-sm">
                  <Row label="沙箱 ID" value={sandbox.sandbox_id} />
                  <Row label="连接" value={sandbox.connection_id ?? '—'} />
                  <Row label="状态" value={sandbox.state} />
                  <Row label="镜像" value={sandbox.image ?? '—'} />
                  <Row label="工作目录" value={sandbox.workdir} />
                </dl>
              ) : (
                <div className="text-muted-foreground">加载中…</div>
              )}
            </Card>
            <Card title="能力">
              {capabilities ? (
                <dl className="space-y-1 text-sm">
                  {Object.entries(capabilities).map(([key, cap]) => (
                    <Row
                      key={key}
                      label={key}
                      value={cap.supported ? '✓ 原生支持' : '✗ 不可用'}
                    />
                  ))}
                </dl>
              ) : (
                <div className="text-muted-foreground">加载中…</div>
              )}
            </Card>
          </div>
        )}
        {tab === 'files' && connectionId && sandboxId && (
          <FilesTab connectionId={connectionId} sandboxId={sandboxId} workdir="/" />
        )}
        {tab === 'commands' && connectionId && sandboxId && (
          <CommandsTab connectionId={connectionId} sandboxId={sandboxId} workdir="/" />
        )}
        {tab === 'history' && connectionId && sandboxId && (
          <HistoryTab connectionId={connectionId} sandboxId={sandboxId} />
        )}
        {tab === 'backups' && connectionId && sandboxId && (
          <BackupsTab connectionId={connectionId} sandboxId={sandboxId} />
        )}
        {tab === 'policies' && sandboxId && (
          <SandboxPoliciesTab sandboxId={sandboxId} />
        )}
      </div>
    </div>
  );
}

// ── Sandbox-level Policies Tab ─────────────────────────────────────

function SandboxPoliciesTab({ sandboxId }: { sandboxId: string }) {
  const queryClient = useQueryClient();
  const [showAddRule, setShowAddRule] = useState(false);

  // Fetch rules for this sandbox via the dedicated endpoint
  const { data, isLoading } = useQuery({
    queryKey: ['sandbox-policies', sandboxId],
    queryFn: async () => {
      try {
        const result = await api.get<{
          group_id: string;
          group_name: string;
          version: number;
          rules: PolicyRule[];
        }>(`/policies/sandbox/${sandboxId}`);
        return result;
      } catch {
        return { group_id: null, group_name: null, version: 0, rules: [] as PolicyRule[] };
      }
    },
  });

  const groupId = data?.group_id ?? null;
  const groupName = data?.group_name ?? null;
  const ruleList = data?.rules ?? [];

  const createRuleMutation = useMutation({
    mutationFn: (data: {
      rule_type: string;
      pattern: string;
      effect: string;
      operations: string;
      priority: number;
      description: string;
    }) =>
      api.post<PolicyRule>(`/policies/groups/${groupId}/rules`, {
        ...data,
        sandbox_id: sandboxId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sandbox-policies', sandboxId] });
      setShowAddRule(false);
    },
  });

  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => api.delete(`/policies/rules/${ruleId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sandbox-policies', sandboxId] });
    },
  });

  const commandRules = ruleList.filter((r) => r.rule_type === 'command');
  const workspaceRules = ruleList.filter((r) => r.rule_type === 'workspace');

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">沙箱权限</h2>
          <p className="text-sm text-muted-foreground">
            {groupName ? `分组: ${groupName}` : '未关联任何权限分组'}
            {' · '}
            沙箱 ID: <span className="font-mono text-xs">{sandboxId}</span>
          </p>
        </div>
        {groupId && (
          <button onClick={() => setShowAddRule(true)} className="btn-primary btn-sm">
            <Plus className="h-4 w-4" />
            添加沙箱级规则
          </button>
        )}
      </div>

      {!groupId && !isLoading && (
        <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
          <Shield className="mx-auto mb-2 h-8 w-8 opacity-50" />
          此沙箱尚未注册到任何权限分组
          <br />
          <span className="text-xs">SDK 创建时使用 policy_group 参数即可自动注册</span>
        </div>
      )}

      {groupId && (
        <>
          {/* Command Rules */}
          <div>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Terminal className="h-4 w-4" />
              命令规则 ({commandRules.length})
            </h3>
            <SandboxRulesTable
              rules={commandRules}
              isLoading={isLoading}
              onDelete={(id) => deleteRuleMutation.mutate(id)}
            />
          </div>

          {/* Workspace Rules */}
          <div>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Folder className="h-4 w-4" />
              路径规则 ({workspaceRules.length})
            </h3>
            <SandboxRulesTable
              rules={workspaceRules}
              isLoading={isLoading}
              onDelete={(id) => deleteRuleMutation.mutate(id)}
            />
          </div>

          {showAddRule && (
            <SandboxRuleForm
              onSubmit={(data) => createRuleMutation.mutate(data)}
              onCancel={() => setShowAddRule(false)}
              loading={createRuleMutation.isPending}
              error={
                createRuleMutation.error instanceof Error
                  ? createRuleMutation.error.message
                  : null
              }
            />
          )}
        </>
      )}
    </div>
  );
}

function SandboxRulesTable({
  rules,
  isLoading,
  onDelete,
}: {
  rules: PolicyRule[];
  isLoading: boolean;
  onDelete: (id: string) => void;
}) {
  if (isLoading) return <div className="text-muted-foreground">加载中…</div>;
  if (rules.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
        暂无规则
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-3 py-2 text-left font-medium">效果</th>
            <th className="px-3 py-2 text-left font-medium">匹配模式</th>
            <th className="px-3 py-2 text-left font-medium">优先级</th>
            <th className="px-3 py-2 text-left font-medium">描述</th>
            <th className="px-3 py-2 text-left font-medium">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {rules.map((r) => (
            <tr key={r.id} className="hover:bg-accent/50">
              <td className="px-3 py-2">
                {r.effect === 'allow' ? (
                  <span className="badge border-green-200 bg-green-100 text-green-700">
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    允许
                  </span>
                ) : (
                  <span className="badge border-red-200 bg-red-100 text-red-700">
                    <AlertCircle className="mr-1 h-3 w-3" />
                    拒绝
                  </span>
                )}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{r.pattern}</td>
              <td className="px-3 py-2 text-center">{r.priority}</td>
              <td className="px-3 py-2 text-muted-foreground">{r.description || '—'}</td>
              <td className="px-3 py-2">
                <button
                  onClick={() => onDelete(r.id)}
                  className="btn-outline btn-sm text-red-600"
                  disabled={r.is_baseline}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SandboxRuleForm({
  onSubmit,
  onCancel,
  loading,
  error,
}: {
  onSubmit: (data: {
    rule_type: string;
    pattern: string;
    effect: string;
    operations: string;
    priority: number;
    description: string;
  }) => void;
  onCancel: () => void;
  loading: boolean;
  error: string | null;
}) {
  const [ruleType, setRuleType] = useState('command');
  const [pattern, setPattern] = useState('');
  const [effect, setEffect] = useState('allow');
  const [operations, setOperations] = useState('read,write,execute');
  const [priority, setPriority] = useState(10);
  const [description, setDescription] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ rule_type: ruleType, pattern, effect, operations, priority, description });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">添加沙箱级规则</h2>
          <button onClick={onCancel} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mb-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">规则类型</label>
            <select className="input" value={ruleType} onChange={(e) => setRuleType(e.target.value)}>
              <option value="command">命令 (Command)</option>
              <option value="workspace">路径 (Workspace)</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              {ruleType === 'command' ? '正则表达式' : '通配符模式'}
            </label>
            <input
              className="input font-mono"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder={ruleType === 'command' ? '^rm\s+-rf' : '/etc/**'}
              required
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium">效果</label>
              <select className="input" value={effect} onChange={(e) => setEffect(e.target.value)}>
                <option value="allow">允许 (Allow)</option>
                <option value="deny">拒绝 (Deny)</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium">优先级</label>
              <input
                className="input"
                type="number"
                value={priority}
                onChange={(e) => setPriority(parseInt(e.target.value, 10) || 0)}
                min={0}
                max={999}
              />
            </div>
          </div>
          {ruleType === 'workspace' && (
            <div>
              <label className="mb-1 block text-sm font-medium">操作类型</label>
              <input
                className="input"
                value={operations}
                onChange={(e) => setOperations(e.target.value)}
                placeholder="read,write,execute"
              />
              <p className="mt-1 text-xs text-muted-foreground">逗号分隔: read, write, execute</p>
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium">描述</label>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="规则说明"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onCancel} className="btn-outline">
              取消
            </button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? '保存中…' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border">
      <div className="border-b bg-muted/50 px-4 py-2 text-sm font-medium">{title}</div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  );
}
