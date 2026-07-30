import { useState } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Pause, Play, Trash2, Folder, Terminal, Info, History, FileArchive } from 'lucide-react';
import { api, type SandboxInfo, type Capabilities } from '@/lib/api';
import { cn } from '@/lib/utils';
import { FilesTab } from '@/features/sandbox-files/FilesTab';
import { CommandsTab } from '@/features/sandbox-commands/CommandsTab';
import { HistoryTab } from '@/features/sandbox-history/HistoryTab';
import { BackupsTab } from '@/features/sandbox-backups/BackupsTab';

type TabId = 'overview' | 'files' | 'commands' | 'history' | 'backups';

const tabs: { id: TabId; label: string; icon: typeof Info }[] = [
  { id: 'overview', label: '概览', icon: Info },
  { id: 'files', label: '文件', icon: Folder },
  { id: 'commands', label: '命令', icon: Terminal },
  { id: 'history', label: '历史', icon: History },
  { id: 'backups', label: '备份', icon: FileArchive },
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
