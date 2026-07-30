import { useState, useMemo, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  Trash2,
  RotateCcw,
  FileArchive,
  ChevronDown,
  ChevronRight,
  Plus,
  X,
  CheckCircle2,
  AlertCircle,
  GitCompare,
  Folder,
  FolderOpen,
  FileText,
  Search,
  Download,
  CheckSquare,
  Square,
  Clock,
  Columns2,
  List,
} from 'lucide-react';
import {
  api,
  type BackupListResponse,
  type BackupFileListResponse,
  type BackupDetail,
  type BackupDiffResponse,
  type BackupItem,
  type BackupRestoreResponse,
  type BackupBatchDeleteResponse,
} from '@/lib/api';
import { cn } from '@/lib/utils';

interface BackupsTabProps {
  connectionId: string;
  sandboxId: string;
}

const triggerColors: Record<string, string> = {
  on_write: 'bg-blue-100 text-blue-700',
  on_delete: 'bg-orange-100 text-orange-700',
  on_command: 'bg-purple-100 text-purple-700',
  manual: 'bg-gray-100 text-gray-700',
  pre_restore: 'bg-amber-100 text-amber-700',
};

const triggerLabels: Record<string, string> = {
  on_write: '写入',
  on_delete: '删除',
  on_command: '命令',
  manual: '手动',
  pre_restore: '回滚前',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString();
}

// ---------------------------------------------------------------------------
// File tree types & builder
// ---------------------------------------------------------------------------

interface BackupFileEntry {
  file_path: string;
  backup_count: number;
  latest_backup_at: string;
}

interface TreeFolder {
  type: 'folder';
  name: string;
  path: string;
  children: Map<string, TreeNode>;
  totalBackups: number;
  latestBackupAt: string;
}

interface TreeFile {
  type: 'file';
  name: string;
  path: string;
  backupCount: number;
  latestBackupAt: string;
  backups: BackupItem[];
}

type TreeNode = TreeFolder | TreeFile;

function buildFileTree(
  files: BackupFileEntry[],
  backupsByPath: Map<string, BackupItem[]>,
): TreeFolder {
  const root: TreeFolder = {
    type: 'folder',
    name: '',
    path: '',
    children: new Map(),
    totalBackups: 0,
    latestBackupAt: '',
  };

  for (const file of files) {
    const parts = file.file_path.split('/').filter(Boolean);
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      const partPath = '/' + parts.slice(0, i + 1).join('/');

      if (isLast) {
        current.children.set(part, {
          type: 'file',
          name: part,
          path: file.file_path,
          backupCount: file.backup_count,
          latestBackupAt: file.latest_backup_at,
          backups: backupsByPath.get(file.file_path) || [],
        });
      } else {
        if (!current.children.has(part)) {
          current.children.set(part, {
            type: 'folder',
            name: part,
            path: partPath,
            children: new Map(),
            totalBackups: 0,
            latestBackupAt: '',
          });
        }
        current = current.children.get(part) as TreeFolder;
      }
    }
  }

  function updateFolder(folder: TreeFolder): void {
    let total = 0;
    let latest = '';
    for (const child of folder.children.values()) {
      if (child.type === 'folder') {
        updateFolder(child);
        total += child.totalBackups;
        if (child.latestBackupAt > latest) latest = child.latestBackupAt;
      } else {
        total += child.backupCount;
        if (child.latestBackupAt > latest) latest = child.latestBackupAt;
      }
    }
    folder.totalBackups = total;
    folder.latestBackupAt = latest;
  }

  updateFolder(root);
  return root;
}

/** Filter the tree by a search query, keeping only matching file nodes (and their parent folders). */
function filterTree(node: TreeFolder, query: string): TreeFolder {
  if (!query) return node;
  const lowerQuery = query.toLowerCase();
  const newChildren = new Map<string, TreeNode>();

  for (const child of node.children.values()) {
    if (child.type === 'folder') {
      const filtered = filterTree(child, query);
      if (filtered.children.size > 0) {
        newChildren.set(child.name, filtered);
      }
    } else {
      if (child.name.toLowerCase().includes(lowerQuery) || child.path.toLowerCase().includes(lowerQuery)) {
        newChildren.set(child.name, child);
      }
    }
  }

  let total = 0;
  let latest = '';
  for (const child of newChildren.values()) {
    if (child.type === 'folder') {
      total += child.totalBackups;
      if (child.latestBackupAt > latest) latest = child.latestBackupAt;
    } else {
      total += child.backupCount;
      if (child.latestBackupAt > latest) latest = child.latestBackupAt;
    }
  }
  return { ...node, children: newChildren, totalBackups: total, latestBackupAt: latest };
}

/** Collect all folder paths from a tree (for auto-expand). */
function collectFolderPaths(folder: TreeFolder): string[] {
  const paths: string[] = [];
  for (const child of folder.children.values()) {
    if (child.type === 'folder') {
      paths.push(child.path);
      paths.push(...collectFolderPaths(child));
    }
  }
  return paths;
}

/** Collect all file paths from a tree (for timeline view). */
function collectFilePaths(folder: TreeFolder): string[] {
  const paths: string[] = [];
  for (const child of folder.children.values()) {
    if (child.type === 'folder') {
      paths.push(...collectFilePaths(child));
    } else {
      paths.push(child.path);
    }
  }
  return paths;
}

// ---------------------------------------------------------------------------
// DiffViewer — supports both unified and side-by-side modes
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
    if (line.startsWith('--- ') || line.startsWith('+++ ')) continue;

    const hunkMatch = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunkMatch) {
      oldLine = parseInt(hunkMatch[1], 10);
      newLine = parseInt(hunkMatch[2], 10);
      continue;
    }
    if (line.startsWith('\\')) {
      result.push({ type: 'meta', content: line, oldLine: null, newLine: null });
      continue;
    }
    if (line.startsWith('+')) {
      result.push({ type: 'add', content: line.slice(1), oldLine: null, newLine: newLine++ });
      continue;
    }
    if (line.startsWith('-')) {
      result.push({ type: 'remove', content: line.slice(1), oldLine: oldLine++, newLine: null });
      continue;
    }
    const content = line.startsWith(' ') ? line.slice(1) : line;
    result.push({ type: 'context', content, oldLine: oldLine++, newLine: newLine++ });
  }
  return result;
}

const lineTypeStyles: Record<DiffLineType, { bg: string; prefix: string; text: string }> = {
  context: { bg: '', prefix: 'text-muted-foreground/40', text: 'text-foreground/80' },
  add: { bg: 'bg-green-50 dark:bg-green-950/40', prefix: 'text-green-600 dark:text-green-400', text: 'text-green-900 dark:text-green-100' },
  remove: { bg: 'bg-red-50 dark:bg-red-950/40', prefix: 'text-red-600 dark:text-red-400', text: 'text-red-900 dark:text-red-100' },
  meta: { bg: '', prefix: 'text-muted-foreground/50', text: 'text-muted-foreground italic' },
};

function DiffViewer({ diff, oldText, newText, sideBySide }: { diff: string; oldText: string | null; newText: string | null; sideBySide: boolean }) {
  const lines = useMemo(() => parseUnifiedDiff(diff), [diff]);
  const stats = useMemo(() => {
    let added = 0;
    let removed = 0;
    for (const l of lines) {
      if (l.type === 'add') added++;
      else if (l.type === 'remove') removed++;
    }
    return { added, removed };
  }, [lines]);

  // Side-by-side rendering
  if (sideBySide && oldText != null && newText != null) {
    const oldLines = oldText.split('\n');
    const newLines = newText.split('\n');
    const maxLen = Math.max(oldLines.length, newLines.length);
    return (
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="flex items-center gap-3 border-b bg-muted/30 px-3 py-2 text-sm">
          <span className="font-mono">
            <span className="text-green-600 dark:text-green-400">+{stats.added}</span>{' '}
            <span className="text-red-600 dark:text-red-400">-{stats.removed}</span>
          </span>
          <span className="text-muted-foreground">{stats.added + stats.removed} 行变更</span>
        </div>
        <div className="max-h-[28rem] overflow-auto font-mono text-sm">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b bg-muted/20">
                <th className="w-1/2 px-3 py-1.5 text-left text-sm font-medium text-muted-foreground">备份版本（旧）</th>
                <th className="w-1/2 px-3 py-1.5 text-left text-sm font-medium text-muted-foreground">对比版本（新）</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: maxLen }, (_, i) => {
                const oldLine = oldLines[i] ?? '';
                const newLine = newLines[i] ?? '';
                // Determine if this line pair has a difference
                const isOldOnly = oldLine && newLine === '' && i >= newLines.length;
                const isNewOnly = newLine && oldLine === '' && i >= oldLines.length;
                const isDiff = oldLine !== newLine && !isOldOnly && !isNewOnly;
                const oldBg = isOldOnly ? 'bg-red-50 dark:bg-red-950/40' : isDiff ? 'bg-red-50/50 dark:bg-red-950/20' : '';
                const newBg = isNewOnly ? 'bg-green-50 dark:bg-green-950/40' : isDiff ? 'bg-green-50/50 dark:bg-green-950/20' : '';
                return (
                  <tr key={i} className="border-b border-border/30">
                    <td className={cn('w-1/2 whitespace-pre-wrap break-all border-r border-border/30 px-3 py-0.5 leading-6', oldBg)}>
                      <span className="mr-2 select-none text-muted-foreground/40">{i + 1}</span>
                      {oldLine || '\u00A0'}
                    </td>
                    <td className={cn('w-1/2 whitespace-pre-wrap break-all px-3 py-0.5 leading-6', newBg)}>
                      <span className="mr-2 select-none text-muted-foreground/40">{i + 1}</span>
                      {newLine || '\u00A0'}
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

  // Unified diff rendering
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center gap-3 border-b bg-muted/30 px-3 py-2 text-sm">
        <span className="font-mono">
          <span className="text-green-600 dark:text-green-400">+{stats.added}</span>{' '}
          <span className="text-red-600 dark:text-red-400">-{stats.removed}</span>
        </span>
        <span className="text-muted-foreground">{stats.added + stats.removed} 行变更</span>
      </div>
      <div className="max-h-[28rem] overflow-auto font-mono text-sm">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, idx) => {
              const style = lineTypeStyles[line.type];
              const prefix = line.type === 'add' ? '+' : line.type === 'remove' ? '-' : '';
              return (
                <tr key={idx} className={cn('border-b border-border/30', style.bg)}>
                  <td className="w-12 select-none whitespace-nowrap border-r border-border/30 px-2 py-0.5 text-right align-top text-muted-foreground/50">{line.oldLine ?? ''}</td>
                  <td className="w-12 select-none whitespace-nowrap border-r border-border/30 px-2 py-0.5 text-right align-top text-muted-foreground/50">{line.newLine ?? ''}</td>
                  <td className={cn('w-5 select-none px-1 py-0.5 text-center align-top', style.prefix)}>{prefix}</td>
                  <td className={cn('whitespace-pre-wrap break-all px-2 py-0.5 leading-6', style.text)}>{line.content || '\u00A0'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline view component
// ---------------------------------------------------------------------------

function TimelineView({ backups, onSelectBackup, selectedBackup }: {
  backups: BackupItem[];
  onSelectBackup: (id: string) => void;
  selectedBackup: string | null;
}) {
  const sorted = useMemo(() => [...backups].sort((a, b) => b.created_at.localeCompare(a.created_at)), [backups]);
  return (
    <div className="rounded-lg border p-4">
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-4 top-0 h-full w-0.5 bg-border" />
        <div className="space-y-4">
          {sorted.map((backup) => {
            const isSelected = selectedBackup === backup.backup_id;
            return (
              <div
                key={backup.backup_id}
                className="relative flex cursor-pointer items-start gap-4"
                onClick={() => onSelectBackup(isSelected ? '' : backup.backup_id)}
              >
                {/* Dot on timeline */}
                <div className={cn(
                  'z-10 mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2',
                  isSelected ? 'border-blue-500 bg-blue-100' : 'border-border bg-background',
                )}>
                  <Clock className="h-4 w-4 text-muted-foreground" />
                </div>
                {/* Content */}
                <div className={cn(
                  'flex-1 rounded-lg border p-3 transition-colors',
                  isSelected ? 'border-blue-300 bg-blue-50/50 dark:bg-blue-950/20' : 'hover:bg-muted/30',
                )}>
                  <div className="flex items-center gap-2">
                    <span className={cn('rounded-full px-2.5 py-0.5 text-sm font-medium', triggerColors[backup.trigger_type] || triggerColors.manual)}>
                      {triggerLabels[backup.trigger_type] || backup.trigger_type}
                    </span>
                    <span className="text-base">{backup.description || '—'}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="font-mono">{backup.backup_id}</span>
                    <span>{formatTime(backup.created_at)}</span>
                    <span>{formatBytes(backup.content_size)}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recursive tree node renderer
// ---------------------------------------------------------------------------

interface MutationProps {
  deleteByPathMutation: { mutate: (filePath: string) => void };
  restoreMutation: { mutate: (backupId: string) => void; isPending: boolean };
}

interface SharedRendererProps extends MutationProps {
  depth: number;
  expandedNodes: Set<string>;
  toggleNode: (path: string) => void;
  selectedBackup: string | null;
  setSelectedBackup: (id: string | null) => void;
  selectedBackupIds: Set<string>;
  toggleBackupSelection: (id: string) => void;
  batchMode: boolean;
  onExport: (backupId: string) => void;
}

interface TreeRendererProps extends SharedRendererProps {
  node: TreeNode;
}

interface TreeFolderProps extends SharedRendererProps {
  node: TreeFolder;
}

interface TreeFileProps extends SharedRendererProps {
  node: TreeFile;
}

function TreeFolderView(props: TreeFolderProps) {
  const { node, depth, expandedNodes, toggleNode } = props;
  const isExpanded = expandedNodes.has(node.path);
  const sortedChildren = Array.from(node.children.values()).sort((a, b) => {
    if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <>
      <div
        className="flex cursor-pointer items-center justify-between border-b border-border/40 px-3 py-2 hover:bg-muted/40"
        style={{ paddingLeft: `${depth * 20 + 12}px` }}
        onClick={() => toggleNode(node.path)}
      >
        <div className="flex items-center gap-2">
          {isExpanded ? <ChevronDown className="h-5 w-5 text-muted-foreground" /> : <ChevronRight className="h-5 w-5 text-muted-foreground" />}
          {isExpanded ? <FolderOpen className="h-5 w-5 text-amber-500" /> : <Folder className="h-5 w-5 text-amber-500" />}
          <span className="font-medium text-base">{node.name}/</span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-sm text-muted-foreground">{node.totalBackups} 个备份</span>
        </div>
        {node.latestBackupAt && (
          <span className="text-sm text-muted-foreground">最新: {formatTime(node.latestBackupAt)}</span>
        )}
      </div>
      {isExpanded && (
        <div>
          {sortedChildren.map((child) => (
            <TreeRenderer key={child.path} {...props} node={child} />
          ))}
        </div>
      )}
    </>
  );
}

function TreeFileView(props: TreeFileProps) {
  const { node, depth, expandedNodes, toggleNode, selectedBackup, setSelectedBackup, selectedBackupIds, toggleBackupSelection, batchMode, restoreMutation, deleteByPathMutation, onExport } = props;
  const isExpanded = expandedNodes.has(node.path);
  const fileBackups = node.backups;

  return (
    <>
      <div
        className="flex cursor-pointer items-center justify-between border-b border-border/40 px-3 py-2 hover:bg-muted/40"
        style={{ paddingLeft: `${depth * 20 + 12}px` }}
        onClick={() => toggleNode(node.path)}
      >
        <div className="flex items-center gap-2">
          {isExpanded ? <ChevronDown className="h-5 w-5 text-muted-foreground" /> : <ChevronRight className="h-5 w-5 text-muted-foreground" />}
          <FileText className="h-5 w-5 text-blue-400" />
          <span className="font-mono text-base">{node.name}</span>
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-sm text-blue-700">{node.backupCount} 个备份</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{formatTime(node.latestBackupAt)}</span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(`确定删除 ${node.path} 的所有备份？`)) {
                deleteByPathMutation.mutate(node.path);
              }
            }}
            className="text-destructive hover:text-destructive/80"
            title="删除该文件的所有备份"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="bg-muted/20">
          {fileBackups.length === 0 ? (
            <div className="px-3 py-2 text-base text-muted-foreground" style={{ paddingLeft: `${(depth + 1) * 20 + 12}px` }}>
              加载备份中…
            </div>
          ) : (
            <div className="divide-y divide-border/30">
              {fileBackups.map((backup: BackupItem) => (
                <div
                  key={backup.backup_id}
                  className="flex items-center justify-between px-3 py-2.5 hover:bg-muted/30"
                  style={{ paddingLeft: `${(depth + 1) * 20 + 12}px` }}
                >
                  <div className="flex items-center gap-3">
                    {batchMode && (
                      <button
                        onClick={() => toggleBackupSelection(backup.backup_id)}
                        className="shrink-0"
                        title="选择此备份"
                      >
                        {selectedBackupIds.has(backup.backup_id) ? (
                          <CheckSquare className="h-5 w-5 text-blue-500" />
                        ) : (
                          <Square className="h-5 w-5 text-muted-foreground" />
                        )}
                      </button>
                    )}
                    <span className={cn('rounded-full px-2.5 py-0.5 text-sm font-medium', triggerColors[backup.trigger_type] || triggerColors.manual)}>
                      {triggerLabels[backup.trigger_type] || backup.trigger_type}
                    </span>
                    <div>
                      <div className="text-base">{backup.description || '—'}</div>
                      <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        <span className="font-mono">{backup.backup_id}</span>
                        <span>{formatTime(backup.created_at)}</span>
                        <span>{formatBytes(backup.content_size)}</span>
                        {backup.actor_id && <span>by {backup.actor_id}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {!batchMode && (
                      <>
                        <button
                          onClick={() => setSelectedBackup(selectedBackup === backup.backup_id ? null : backup.backup_id)}
                          className="btn-ghost btn-sm"
                          title="查看变更"
                        >
                          <GitCompare className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => onExport(backup.backup_id)}
                          className="btn-ghost btn-sm"
                          title="导出备份文件"
                        >
                          <Download className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`确定将 ${backup.file_path} 回滚到此版本？\n当前文件内容将被覆盖。系统会自动备份当前版本，以便撤销。`)) {
                              restoreMutation.mutate(backup.backup_id);
                            }
                          }}
                          className="btn-ghost btn-sm text-blue-600"
                          title="回滚到此版本"
                          disabled={restoreMutation.isPending}
                        >
                          <RotateCcw className="h-4 w-4" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function TreeRenderer(props: TreeRendererProps) {
  const { node, ...rest } = props;
  if (node.type === 'folder') {
    return <TreeFolderView node={node} {...rest} />;
  }
  return <TreeFileView node={node} {...rest} />;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type ViewMode = 'tree' | 'timeline';

export function BackupsTab({ connectionId, sandboxId }: BackupsTabProps) {
  const queryClient = useQueryClient();
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedBackup, setSelectedBackup] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createPath, setCreatePath] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [batchMode, setBatchMode] = useState(false);
  const [selectedBackupIds, setSelectedBackupIds] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>('tree');
  const [timelineFilePath, setTimelineFilePath] = useState<string | null>(null);
  const [diffMode, setDiffMode] = useState<'unified' | 'split'>('split');
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const basePath = `/connections/${connectionId}/sandboxes/${sandboxId}/backups`;

  const showToast = useCallback((type: 'success' | 'error', message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 5000);
  }, []);

  const { data: filesData, isLoading: filesLoading } = useQuery({
    queryKey: ['backup-files', connectionId, sandboxId],
    queryFn: () => api.get<BackupFileListResponse>(`${basePath}/files`),
    refetchInterval: 15_000,
  });

  const { data: backupsData } = useQuery({
    queryKey: ['backups', connectionId, sandboxId],
    queryFn: () => api.get<BackupListResponse>(`${basePath}?limit=500`),
    refetchInterval: 15_000,
  });

  const { data: backupDetail } = useQuery({
    queryKey: ['backup-detail', connectionId, sandboxId, selectedBackup],
    queryFn: () => api.get<BackupDetail>(`${basePath}/${selectedBackup}?include_content=true`),
    enabled: !!selectedBackup,
  });

  const { data: backupDiff, isLoading: diffLoading, isError: diffError } = useQuery({
    queryKey: ['backup-diff', connectionId, sandboxId, selectedBackup, diffMode],
    queryFn: () =>
      api.get<BackupDiffResponse>(`${basePath}/${selectedBackup}/diff?side_by_side=${diffMode === 'split'}`),
    enabled: !!selectedBackup,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: () => api.post(basePath, { file_path: createPath, description: createDesc }),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['backups', connectionId, sandboxId] });
      queryClient.invalidateQueries({ queryKey: ['backup-files', connectionId, sandboxId] });
      setShowCreateModal(false);
      setCreatePath('');
      setCreateDesc('');
      if (data?.created) showToast('success', '备份创建成功');
      else showToast('error', data?.message || '备份创建失败');
    },
    onError: () => showToast('error', '备份创建失败'),
  });

  const restoreMutation = useMutation({
    mutationFn: (backupId: string) => api.post<BackupRestoreResponse>(`${basePath}/${backupId}/restore`),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['backups', connectionId, sandboxId] });
      queryClient.invalidateQueries({ queryKey: ['backup-files', connectionId, sandboxId] });
      queryClient.invalidateQueries({ queryKey: ['files', connectionId, sandboxId] });
      if (data?.restored) showToast('success', data.message || `文件 ${data.file_path} 已回滚成功`);
      else showToast('error', '回滚失败');
    },
    onError: () => showToast('error', '回滚失败，请重试'),
  });

  const deleteByPathMutation = useMutation({
    mutationFn: (filePath: string) => api.delete(`${basePath}?file_path=${encodeURIComponent(filePath)}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backups', connectionId, sandboxId] });
      queryClient.invalidateQueries({ queryKey: ['backup-files', connectionId, sandboxId] });
      showToast('success', '已删除该文件的所有备份');
    },
    onError: () => showToast('error', '删除备份失败'),
  });

  const batchDeleteMutation = useMutation({
    mutationFn: (backupIds: string[]) =>
      api.post<BackupBatchDeleteResponse>(`${basePath}/batch-delete`, { backup_ids: backupIds }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['backups', connectionId, sandboxId] });
      queryClient.invalidateQueries({ queryKey: ['backup-files', connectionId, sandboxId] });
      showToast('success', `已删除 ${data.deleted} 个备份${data.failed > 0 ? `，${data.failed} 个失败` : ''}`);
      setBatchMode(false);
      setSelectedBackupIds(new Set());
    },
    onError: () => showToast('error', '批量删除失败'),
  });

  const toggleNode = (path: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const toggleBackupSelection = (id: string) => {
    setSelectedBackupIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleExport = (backupId: string) => {
    const url = `/api/v1${basePath}/${backupId}/export`;
    window.open(url, '_blank');
    showToast('success', '开始下载备份文件');
  };

  // Group backups by file_path
  const backupsByPath = useMemo(() => {
    const map = new Map<string, BackupItem[]>();
    if (backupsData?.backups) {
      for (const b of backupsData.backups) {
        const existing = map.get(b.file_path) || [];
        existing.push(b);
        map.set(b.file_path, existing);
      }
    }
    return map;
  }, [backupsData]);

  // Build file tree
  const fileTree = useMemo(() => {
    const fileEntries = filesData?.files || [];
    return buildFileTree(fileEntries as BackupFileEntry[], backupsByPath);
  }, [filesData, backupsByPath]);

  // Apply search filter
  const filteredTree = useMemo(() => filterTree(fileTree, searchQuery), [fileTree, searchQuery]);

  // Auto-expand all folder nodes on first load or when searching
  useEffect(() => {
    if (filesData !== undefined && filteredTree.children.size > 0) {
      const allPaths = collectFolderPaths(filteredTree);
      // When searching, always expand all to show results
      // On first load, expand all if not yet expanded
      if (searchQuery || expandedNodes.size === 0) {
        setExpandedNodes(new Set(allPaths));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filesData, searchQuery]);

  const fileCount = filesData?.total || 0;
  const sortedTopLevel = useMemo(() => Array.from(filteredTree.children.values()).sort((a, b) => {
    if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
    return a.name.localeCompare(b.name);
  }), [filteredTree]);

  // Timeline data: if a file is selected, show its backups
  const timelineBackups = useMemo(() => {
    if (!timelineFilePath) return [];
    return backupsByPath.get(timelineFilePath) || [];
  }, [timelineFilePath, backupsByPath]);

  const allFilePaths = useMemo(() => collectFilePaths(fileTree), [fileTree]);

  return (
    <div className="flex h-full flex-col">
      {/* Toast notification */}
      {toast && (
        <div className={cn('flex items-center gap-2 border-b px-4 py-3 text-base', toast.type === 'success' ? 'border-green-200 bg-green-50 text-green-700' : 'border-red-200 bg-red-50 text-red-700')}>
          {toast.type === 'success' ? <CheckCircle2 className="h-5 w-5 shrink-0" /> : <AlertCircle className="h-5 w-5 shrink-0" />}
          <span className="flex-1">{toast.message}</span>
          <button onClick={() => setToast(null)} className="shrink-0"><X className="h-4 w-4" /></button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <FileArchive className="h-5 w-5 text-muted-foreground" />
          <span className="text-base font-medium">文件备份</span>
          {fileCount > 0 && (
            <span className="text-sm text-muted-foreground">{fileCount} 个文件 · {backupsData?.total || 0} 个备份</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex rounded-md border">
            <button
              onClick={() => setViewMode('tree')}
              className={cn('flex items-center gap-1 px-3 py-1 text-sm', viewMode === 'tree' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted')}
              title="文件树视图"
            >
              <List className="h-4 w-4" /> 树形
            </button>
            <button
              onClick={() => setViewMode('timeline')}
              className={cn('flex items-center gap-1 px-3 py-1 text-sm', viewMode === 'timeline' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted')}
              title="时间线视图"
            >
              <Clock className="h-4 w-4" /> 时间线
            </button>
          </div>
          <button
            onClick={() => { setBatchMode(!batchMode); if (batchMode) setSelectedBackupIds(new Set()); }}
            className={cn('btn-outline btn-sm', batchMode && 'border-blue-500 text-blue-600')}
          >
            <CheckSquare className="h-4 w-4" /> {batchMode ? '退出批量' : '批量操作'}
          </button>
          <button onClick={() => queryClient.invalidateQueries({ queryKey: ['backups', connectionId, sandboxId] })} className="btn-outline btn-sm">
            <RefreshCw className="h-4 w-4" /> 刷新
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn-outline btn-sm">
            <Plus className="h-4 w-4" /> 创建备份
          </button>
        </div>
      </div>

      {/* Batch action bar */}
      {batchMode && (
        <div className="flex items-center justify-between border-b bg-blue-50/50 px-4 py-2 dark:bg-blue-950/20">
          <span className="text-base text-blue-700 dark:text-blue-300">
            已选择 {selectedBackupIds.size} 个备份
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => {
                if (selectedBackupIds.size === 0) { showToast('error', '请先选择备份'); return; }
                if (confirm(`确定删除选中的 ${selectedBackupIds.size} 个备份？`)) {
                  batchDeleteMutation.mutate(Array.from(selectedBackupIds));
                }
              }}
              disabled={batchDeleteMutation.isPending}
              className="btn-outline btn-sm text-destructive"
            >
              <Trash2 className="h-4 w-4" /> 删除选中
            </button>
          </div>
        </div>
      )}

      {/* Search bar (tree mode only) */}
      {viewMode === 'tree' && fileCount > 0 && (
        <div className="border-b px-4 py-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索文件名…"
              className="w-full rounded-md border py-2 pl-9 pr-9 text-base"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2">
                <X className="h-4 w-4 text-muted-foreground" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Timeline file selector */}
      {viewMode === 'timeline' && (
        <div className="border-b px-4 py-2">
          <select
            value={timelineFilePath || ''}
            onChange={(e) => setTimelineFilePath(e.target.value || null)}
            className="w-full rounded-md border px-3 py-2 text-base"
          >
            <option value="">— 选择文件查看时间线 —</option>
            {allFilePaths.map((path) => (
              <option key={path} value={path}>{path}</option>
            ))}
          </select>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {filesLoading ? (
          <div className="text-center text-base text-muted-foreground">加载备份中…</div>
        ) : fileCount === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <FileArchive className="mb-2 h-10 w-10 opacity-50" />
            <p className="text-base">暂无文件备份</p>
            <p className="mt-1 text-sm">当 Agent 写入或删除文件时会自动创建备份，您也可以手动创建备份。</p>
          </div>
        ) : viewMode === 'timeline' ? (
          timelineFilePath ? (
            timelineBackups.length > 0 ? (
              <TimelineView
                backups={timelineBackups}
                onSelectBackup={(id) => setSelectedBackup(id || null)}
                selectedBackup={selectedBackup}
              />
            ) : (
              <div className="text-center text-base text-muted-foreground">该文件暂无备份</div>
            )
          ) : (
            <div className="text-center text-base text-muted-foreground">请选择一个文件查看其版本时间线</div>
          )
        ) : sortedTopLevel.length === 0 ? (
          <div className="text-center text-base text-muted-foreground">未找到匹配的文件</div>
        ) : (
          <div className="rounded-lg border">
            {sortedTopLevel.map((node) => (
              <TreeRenderer
                key={node.path}
                node={node}
                depth={0}
                expandedNodes={expandedNodes}
                toggleNode={toggleNode}
                selectedBackup={selectedBackup}
                setSelectedBackup={setSelectedBackup}
                selectedBackupIds={selectedBackupIds}
                toggleBackupSelection={toggleBackupSelection}
                batchMode={batchMode}
                deleteByPathMutation={deleteByPathMutation}
                restoreMutation={restoreMutation}
                onExport={handleExport}
              />
            ))}
          </div>
        )}
      </div>

      {/* Backup Detail Drawer */}
      {selectedBackup && backupDetail && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-black/30" onClick={() => setSelectedBackup(null)} />
          <div className="w-1/2 overflow-auto border-l bg-background p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-medium">备份详情</h3>
              <button onClick={() => setSelectedBackup(null)} className="btn-ghost btn-sm"><X className="h-5 w-5" /></button>
            </div>
            <dl className="space-y-2 text-base">
              <div className="flex justify-between"><dt className="text-muted-foreground">备份 ID</dt><dd className="font-mono">{backupDetail.backup_id}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">文件路径</dt><dd className="font-mono">{backupDetail.file_path}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">大小</dt><dd>{formatBytes(backupDetail.content_size)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">哈希</dt><dd className="font-mono text-sm">{backupDetail.content_hash}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">触发类型</dt><dd>{triggerLabels[backupDetail.trigger_type] || backupDetail.trigger_type}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">创建时间</dt><dd>{formatTime(backupDetail.created_at)}</dd></div>
              {backupDetail.description && (<div className="flex justify-between"><dt className="text-muted-foreground">描述</dt><dd>{backupDetail.description}</dd></div>)}
              {backupDetail.actor_id && (<div className="flex justify-between"><dt className="text-muted-foreground">操作者</dt><dd>{backupDetail.actor_type} / {backupDetail.actor_id}</dd></div>)}
              {backupDetail.command && (<div className="flex justify-between"><dt className="text-muted-foreground">命令</dt><dd className="font-mono text-sm">{backupDetail.command}</dd></div>)}
            </dl>

            {/* Action buttons */}
            <div className="mt-5 flex gap-2">
              <button
                onClick={() => {
                  if (confirm(`确定将 ${backupDetail.file_path} 回滚到此版本？\n当前文件内容将被覆盖。系统会自动备份当前版本，以便撤销。`)) {
                    restoreMutation.mutate(backupDetail.backup_id);
                    setSelectedBackup(null);
                  }
                }}
                disabled={restoreMutation.isPending}
                className="btn-primary btn-sm flex items-center gap-1.5"
              >
                <RotateCcw className="h-4 w-4" />
                {restoreMutation.isPending ? '回滚中…' : '回滚到此版本'}
              </button>
              <button onClick={() => handleExport(backupDetail.backup_id)} className="btn-outline btn-sm flex items-center gap-1.5">
                <Download className="h-4 w-4" /> 导出
              </button>
            </div>

            {/* Git-style diff section */}
            <div className="mt-5">
              <div className="mb-2 flex items-center gap-2">
                <GitCompare className="h-4 w-4 text-muted-foreground" />
                <span className="text-base font-medium">备份后的变更</span>
                {backupDiff && <span className="text-sm text-muted-foreground">（对比: {backupDiff.comparison_source}）</span>}
                {/* Diff mode toggle */}
                <div className="ml-auto flex rounded-md border">
                  <button onClick={() => setDiffMode('split')} className={cn('flex items-center gap-1 px-2 py-1 text-sm', diffMode === 'split' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted')} title="双栏对比">
                    <Columns2 className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => setDiffMode('unified')} className={cn('flex items-center gap-1 px-2 py-1 text-sm', diffMode === 'unified' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted')} title="合并视图">
                    <List className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {diffLoading ? (
                <div className="py-4 text-center text-base text-muted-foreground">正在计算变更…</div>
              ) : diffError ? (
                <div className="py-4 text-center text-base text-red-500">变更计算失败，请稍后重试</div>
              ) : backupDiff?.is_binary ? (
                <div className="py-4 text-center text-base text-muted-foreground">二进制文件，无法显示变更</div>
              ) : backupDiff?.has_diff && backupDiff.diff ? (
                <DiffViewer diff={backupDiff.diff} oldText={backupDiff.old_text} newText={backupDiff.new_text} sideBySide={diffMode === 'split'} />
              ) : (
                <div className="py-4 text-center text-base text-muted-foreground">
                  {backupDiff?.comparison_source === 'file deleted' ? '文件已被删除，无后续变更' : backupDiff?.is_latest ? '此为最新备份，文件内容与当前一致，无后续变更' : '此版本与下一版本内容一致，无变更'}
                </div>
              )}
            </div>

            {/* Backup content preview */}
            {backupDetail.content_base64 && (
              <details className="mt-5">
                <summary className="mb-2 cursor-pointer text-base font-medium">备份原始内容</summary>
                <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-sm leading-6">
                  {(() => {
                    try {
                      const binary = atob(backupDetail.content_base64);
                      const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
                      const decoded = new TextDecoder('utf-8').decode(bytes);
                      return decoded.substring(0, 8192);
                    } catch { return '[二进制内容或无效的 base64]'; }
                  })()}
                  {backupDetail.content_size > 8192 && '\n... [已截断]'}
                </pre>
              </details>
            )}
          </div>
        </div>
      )}

      {/* Create Backup Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[28rem] rounded-md border bg-background p-5 shadow-lg">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-medium">创建手动备份</h3>
              <button onClick={() => setShowCreateModal(false)} className="btn-ghost btn-sm"><X className="h-5 w-5" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-base text-muted-foreground">文件路径</label>
                <input type="text" value={createPath} onChange={(e) => setCreatePath(e.target.value)} placeholder="/workspace/main.py" className="input w-full" />
              </div>
              <div>
                <label className="mb-1.5 block text-base text-muted-foreground">描述（可选）</label>
                <input type="text" value={createDesc} onChange={(e) => setCreateDesc(e.target.value)} placeholder="重构前备份" className="input w-full" />
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => setShowCreateModal(false)} className="btn-outline btn-sm">取消</button>
                <button onClick={() => createMutation.mutate()} disabled={!createPath || createMutation.isPending} className="btn-primary btn-sm">
                  {createMutation.isPending ? '创建中…' : '创建'}
                </button>
              </div>
              {createMutation.data && !createMutation.data.created && (
                <p className="text-sm text-destructive">{createMutation.data.message || '备份创建失败'}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
