import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield,
  Plus,
  RefreshCw,
  Trash2,
  Pencil,
  X,
  Send,
  AlertCircle,
  CheckCircle2,
  Zap,
  FolderCog,
  Terminal,
  FileText,
} from 'lucide-react';
import { api, type PolicyGroup, type PolicyRule } from '@/lib/api';
import { cn } from '@/lib/utils';

export function PoliciesPage() {
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['policy-groups'],
    queryFn: () => api.get<PolicyGroup[]>('/policies/groups'),
    refetchInterval: 30_000,
  });

  const createGroupMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) =>
      api.post<PolicyGroup>('/policies/groups', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policy-groups'] });
    },
  });

  const deleteGroupMutation = useMutation({
    mutationFn: (groupId: string) => api.delete(`/policies/groups/${groupId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policy-groups'] });
      setSelectedGroupId(null);
    },
  });

  const pushMutation = useMutation({
    mutationFn: (groupId: string) =>
      api.post<{ pushed: number; failed: number; version: number }>('/policies/push', { group_id: groupId }),
    onSuccess: (_, groupId) => {
      queryClient.invalidateQueries({ queryKey: ['policy-groups'] });
      queryClient.invalidateQueries({ queryKey: ['policy-rules', groupId] });
    },
  });

  return (
    <div className="flex h-full gap-4">
      {/* Left: Group List */}
      <div className="flex w-80 flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            <h1 className="text-lg font-semibold">权限管理</h1>
          </div>
          <button
            onClick={() => {
              const name = prompt('分组名称:');
              if (name) {
                createGroupMutation.mutate({ name, description: '' });
              }
            }}
            className="btn-primary btn-sm"
          >
            <Plus className="h-4 w-4" />
            新建分组
          </button>
        </div>

        {isLoading ? (
          <div className="text-muted-foreground">加载中…</div>
        ) : groups.length === 0 ? (
          <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
            <FolderCog className="mx-auto mb-2 h-8 w-8 opacity-50" />
            暂无权限分组
            <br />
            <span className="text-xs">SDK 注册时会自动创建分组</span>
          </div>
        ) : (
          <div className="flex-1 space-y-1 overflow-auto">
            {groups.map((g) => (
              <div
                key={g.id}
                onClick={() => setSelectedGroupId(g.id)}
                className={cn(
                  'cursor-pointer rounded-md border p-3 transition-colors',
                  selectedGroupId === g.id
                    ? 'border-primary bg-secondary'
                    : 'border-border hover:bg-accent/50',
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{g.name}</span>
                  <div className="flex items-center gap-1">
                    <span className="badge border-blue-200 bg-blue-100 text-blue-700 text-xs">
                      v{g.version}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {g.rule_count} 条规则
                    </span>
                  </div>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {g.description || '无描述'}
                </p>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <span>SDK 注册数: {g.registration_count}</span>
                  {g.enabled ? (
                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                  ) : (
                    <span className="text-red-500">已禁用</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Right: Group Detail */}
      {selectedGroupId ? (
        <GroupDetail
          groupId={selectedGroupId}
          onPush={() => pushMutation.mutate(selectedGroupId)}
          pushResult={pushMutation.data}
          pushLoading={pushMutation.isPending}
          onDelete={() => deleteGroupMutation.mutate(selectedGroupId)}
        />
      ) : (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <div className="text-center">
            <Shield className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p>选择左侧的分组查看详情</p>
          </div>
        </div>
      )}
    </div>
  );
}

function GroupDetail({
  groupId,
  onPush,
  pushResult,
  pushLoading,
  onDelete,
}: {
  groupId: string;
  onPush: () => void;
  pushResult?: { pushed: number; failed: number; version: number };
  pushLoading: boolean;
  onDelete: () => void;
}) {
  const queryClient = useQueryClient();
  const [showAddRule, setShowAddRule] = useState(false);
  const [editingRule, setEditingRule] = useState<PolicyRule | null>(null);

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['policy-rules', groupId],
    queryFn: () => api.get<PolicyRule[]>(`/policies/groups/${groupId}/rules`),
    refetchInterval: 15_000,
  });

  const createRuleMutation = useMutation({
    mutationFn: (data: {
      rule_type: string;
      pattern: string;
      effect: string;
      operations: string;
      priority: number;
      description: string;
      sandbox_id?: string | null;
    }) => api.post<PolicyRule>(`/policies/groups/${groupId}/rules`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policy-rules', groupId] });
      setShowAddRule(false);
    },
  });

  const updateRuleMutation = useMutation({
    mutationFn: (data: {
      id: string;
      pattern: string;
      effect: string;
      operations: string;
      priority: number;
      description: string;
    }) =>
      api.put<PolicyRule>(`/policies/rules/${data.id}`, {
        pattern: data.pattern,
        effect: data.effect,
        operations: data.operations,
        priority: data.priority,
        description: data.description,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policy-rules', groupId] });
      setEditingRule(null);
    },
  });

  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => api.delete(`/policies/rules/${ruleId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policy-rules', groupId] });
    },
  });

  const commandRules = rules.filter((r) => r.rule_type === 'command');
  const workspaceRules = rules.filter((r) => r.rule_type === 'workspace');

  return (
    <div className="flex-1 space-y-4 overflow-auto">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">规则详情</h2>
        <div className="flex gap-2">
          <button onClick={onPush} disabled={pushLoading} className="btn-primary btn-sm">
            <Send className={cn('h-4 w-4', pushLoading && 'animate-spin')} />
            推送策略
          </button>
          <button onClick={() => setShowAddRule(true)} className="btn-outline btn-sm">
            <Plus className="h-4 w-4" />
            添加规则
          </button>
          <button
            onClick={() => {
              if (confirm('确认删除此分组及其所有规则？')) {
                onDelete();
              }
            }}
            className="btn-outline btn-sm text-red-600"
          >
            <Trash2 className="h-4 w-4" />
            删除分组
          </button>
        </div>
      </div>

      {pushResult && (
        <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700">
          推送完成: 成功 {pushResult.pushed}, 失败 {pushResult.failed}, 版本 v{pushResult.version}
        </div>
      )}

      {/* Command Rules */}
      <div>
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <Terminal className="h-4 w-4" />
          命令规则 ({commandRules.length})
        </h3>
        <RulesTable
          rules={commandRules}
          isLoading={isLoading}
          onEdit={setEditingRule}
          onDelete={(id) => deleteRuleMutation.mutate(id)}
        />
      </div>

      {/* Workspace Rules */}
      <div>
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <FileText className="h-4 w-4" />
          路径规则 ({workspaceRules.length})
        </h3>
        <RulesTable
          rules={workspaceRules}
          isLoading={isLoading}
          onEdit={setEditingRule}
          onDelete={(id) => deleteRuleMutation.mutate(id)}
        />
      </div>

      {(showAddRule || editingRule) && (
        <RuleForm
          rule={editingRule}
          onSubmit={(data) => {
            if (editingRule) {
              updateRuleMutation.mutate({ ...data, id: editingRule.id });
            } else {
              createRuleMutation.mutate(data);
            }
          }}
          onCancel={() => {
            setShowAddRule(false);
            setEditingRule(null);
          }}
          loading={createRuleMutation.isPending || updateRuleMutation.isPending}
          error={
            createRuleMutation.error instanceof Error
              ? createRuleMutation.error.message
              : updateRuleMutation.error instanceof Error
                ? updateRuleMutation.error.message
                : null
          }
        />
      )}
    </div>
  );
}

function RulesTable({
  rules,
  isLoading,
  onEdit,
  onDelete,
}: {
  rules: PolicyRule[];
  isLoading: boolean;
  onEdit: (rule: PolicyRule) => void;
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
            <th className="px-3 py-2 text-left font-medium">范围</th>
            <th className="px-3 py-2 text-left font-medium">描述</th>
            <th className="px-3 py-2 text-left font-medium">类型</th>
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
              <td className="px-3 py-2">
                {r.sandbox_id ? (
                  <span className="font-mono text-xs text-blue-600" title={r.sandbox_id}>
                    {r.sandbox_id.slice(0, 8)}…
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">全部分组</span>
                )}
              </td>
              <td className="px-3 py-2 text-muted-foreground">{r.description || '—'}</td>
              <td className="px-3 py-2">
                {r.is_baseline ? (
                  <span className="badge border-orange-200 bg-orange-100 text-orange-700 text-xs">
                    <Zap className="mr-1 h-3 w-3" />
                    Baseline
                  </span>
                ) : null}
              </td>
              <td className="px-3 py-2">
                <div className="flex gap-1">
                  <button
                    onClick={() => onEdit(r)}
                    className="btn-outline btn-sm"
                    disabled={r.is_baseline}
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                  <button
                    onClick={() => onDelete(r.id)}
                    className="btn-outline btn-sm text-red-600"
                    disabled={r.is_baseline}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RuleForm({
  rule,
  onSubmit,
  onCancel,
  loading,
  error,
}: {
  rule: PolicyRule | null;
  onSubmit: (data: {
    rule_type: string;
    pattern: string;
    effect: string;
    operations: string;
    priority: number;
    description: string;
    sandbox_id?: string | null;
  }) => void;
  onCancel: () => void;
  loading: boolean;
  error: string | null;
}) {
  const [ruleType, setRuleType] = useState(rule?.rule_type ?? 'command');
  const [pattern, setPattern] = useState(rule?.pattern ?? '');
  const [effect, setEffect] = useState(rule?.effect ?? 'allow');
  const [operations, setOperations] = useState(rule?.operations ?? 'read,write,execute');
  const [priority, setPriority] = useState(rule?.priority ?? 10);
  const [description, setDescription] = useState(rule?.description ?? '');
  const [sandboxId, setSandboxId] = useState(rule?.sandbox_id ?? '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      rule_type: ruleType,
      pattern,
      effect,
      operations,
      priority,
      description,
      sandbox_id: sandboxId || null,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{rule ? '编辑规则' : '添加规则'}</h2>
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
              placeholder={ruleType === 'command' ? '^rm\\s+-rf' : '/etc/**'}
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
          {!rule && (
            <div>
              <label className="mb-1 block text-sm font-medium">沙箱 ID（可选）</label>
              <input
                className="input font-mono text-xs"
                value={sandboxId}
                onChange={(e) => setSandboxId(e.target.value)}
                placeholder="留空 = 适用于分组内所有沙箱"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                填写特定沙箱 ID 则此规则仅对该沙箱生效（沙箱级覆盖）
              </p>
            </div>
          )}
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
