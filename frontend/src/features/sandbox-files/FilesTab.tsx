import { useState, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Folder, File as FileIcon, ChevronRight, ChevronDown, Save, Upload, Download, FolderPlus, X, AlertCircle, FolderOpen,
} from 'lucide-react';
import Editor from '@monaco-editor/react';
import { api, type FileEntry, type FileContent, type FileWriteResult } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';

interface FilesTabProps {
  connectionId: string;
  sandboxId: string;
  workdir: string;
}

export function FilesTab({ connectionId, sandboxId, workdir }: FilesTabProps) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState('');
  const [dirty, setDirty] = useState(false);
  const queryClient = useQueryClient();

  // Load file content when selected.
  const { data: fileData, isLoading: fileLoading } = useQuery({
    queryKey: ['file', connectionId, sandboxId, selectedPath],
    queryFn: () =>
      api.get<FileContent>(
        `/connections/${connectionId}/sandboxes/${sandboxId}/file?path=${encodeURIComponent(selectedPath!)}`,
      ),
    enabled: !!selectedPath,
  });

  // Update editor when file data changes.
  if (fileData && editorContent === '' && !dirty) {
    setEditorContent(fileData.content);
  }

  const saveMutation = useMutation({
    mutationFn: (content: string) => {
      const expectedHash = fileData?.content_hash;
      return api.put<FileWriteResult>(
        `/connections/${connectionId}/sandboxes/${sandboxId}/file?path=${encodeURIComponent(selectedPath!)}&If-Match=${expectedHash ?? ''}`,
        { content, expected_hash: expectedHash },
      );
    },
    onSuccess: () => {
      setDirty(false);
      queryClient.invalidateQueries({
        queryKey: ['file', connectionId, sandboxId, selectedPath],
      });
      queryClient.invalidateQueries({
        queryKey: ['files', connectionId, sandboxId],
      });
    },
  });

  const handleSave = () => {
    if (selectedPath && dirty) {
      saveMutation.mutate(editorContent);
    }
  };

  const handleSelect = (path: string) => {
    if (dirty) {
      if (!confirm('Unsaved changes will be lost. Continue?')) return;
    }
    setSelectedPath(path);
    setEditorContent('');
    setDirty(false);
  };

  // --- Upload ---
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sessionToken = useAuthStore((s) => s.sessionToken);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async ({ file, destPath }: { file: File; destPath: string }) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('path', destPath);
      const resp = await fetch(
        `/api/v1/connections/${connectionId}/sandboxes/${sandboxId}/upload`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${sessionToken}` },
          body: formData,
          credentials: 'include',
        },
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err?.error?.message ?? `Upload failed: ${resp.status}`);
      }
      return resp.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['files', connectionId, sandboxId] });
      setShowUploadDialog(false);
      setPendingFile(null);
    },
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPendingFile(file);
    setShowUploadDialog(true);
    // Reset input so the same file can be uploaded again.
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // --- Download ---
  const handleDownload = async () => {
    if (!selectedPath) return;
    const resp = await fetch(
      `/api/v1/connections/${connectionId}/sandboxes/${sandboxId}/download?path=${encodeURIComponent(selectedPath)}`,
      { headers: { Authorization: `Bearer ${sessionToken}` }, credentials: 'include' },
    );
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = selectedPath.split('/').pop() ?? 'download';
    a.click();
    URL.revokeObjectURL(url);
  };

  // --- New Folder ---
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderError, setNewFolderError] = useState<string | null>(null);

  const newFolderMutation = useMutation({
    mutationFn: (folderPath: string) =>
      api.post(`/connections/${connectionId}/sandboxes/${sandboxId}/commands`, {
        command: `mkdir -p ${folderPath}`,
        mode: 'foreground',
        timeout_seconds: 10,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['files', connectionId, sandboxId],
      });
      setShowNewFolderDialog(false);
      setNewFolderName('');
      setNewFolderError(null);
    },
    onError: (err: unknown) => {
      setNewFolderError(err instanceof Error ? err.message : 'Failed to create folder');
    },
  });

  const handleNewFolder = () => {
    setNewFolderName('');
    setNewFolderError(null);
    setShowNewFolderDialog(true);
  };

  const handleNewFolderSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const name = newFolderName.trim();
    if (!name) return;
    // Sanitize: remove leading/trailing slashes, reject path traversal.
    const cleanName = name.replace(/^\/+|\/+$/g, '');
    if (cleanName.includes('..')) {
      setNewFolderError('Invalid folder name');
      return;
    }
    const folderPath = workdir === '/' ? `/${cleanName}` : `${workdir}/${cleanName}`;
    newFolderMutation.mutate(folderPath);
  };

  return (
    <div className="flex h-full">
      {/* File Tree */}
      <div className="w-64 overflow-auto border-r p-2">
        <div className="mb-2 flex items-center gap-1">
          <span className="text-xs font-medium text-muted-foreground flex-1">Files</span>
          <button
            onClick={handleNewFolder}
            disabled={newFolderMutation.isPending}
            className="btn-outline btn-sm"
            title="New folder"
          >
            <FolderPlus className="h-3 w-3" />
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="btn-outline btn-sm"
            title="Upload file"
          >
            <Upload className="h-3 w-3" />
            {uploadMutation.isPending ? '…' : ''}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileSelect}
          />
        </div>
        {uploadMutation.isError && (
          <div className="mb-2 rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">
            Upload failed: {uploadMutation.error instanceof Error ? uploadMutation.error.message : 'Unknown'}
          </div>
        )}
        <FileTree
          connectionId={connectionId}
          sandboxId={sandboxId}
          path={workdir}
          level={0}
          selectedPath={selectedPath}
          onSelect={handleSelect}
        />
      </div>

      {/* Editor */}
      <div className="flex flex-1 flex-col">
        {selectedPath ? (
          <>
            <div className="flex items-center justify-between border-b px-4 py-1.5">
              <span className="font-mono text-sm text-muted-foreground">{selectedPath}</span>
              <div className="flex items-center gap-2">
                {dirty && (
                  <span className="text-xs text-yellow-600">● modified</span>
                )}
                {saveMutation.isError && (
                  <span className="text-xs text-destructive">Save failed (conflict?)</span>
                )}
                <button
                  onClick={handleSave}
                  disabled={!dirty || saveMutation.isPending}
                  className="btn-primary btn-sm"
                >
                  <Save className="h-3 w-3" /> Save
                </button>
                <button
                  onClick={handleDownload}
                  className="btn-outline btn-sm"
                  title="Download file"
                >
                  <Download className="h-3 w-3" /> Download
                </button>
              </div>
            </div>
            {fileLoading ? (
              <div className="flex flex-1 items-center justify-center text-muted-foreground">
                Loading…
              </div>
            ) : fileData?.is_binary ? (
              <div className="flex flex-col flex-1 items-center justify-center gap-2 text-muted-foreground">
                <span>Binary file — cannot be displayed in editor.</span>
                <button onClick={handleDownload} className="btn-outline btn-sm">
                  <Download className="h-3 w-3" /> Download File
                </button>
              </div>
            ) : (
              <Editor
                height="100%"
                defaultLanguage="python"
                language={detectLanguage(selectedPath)}
                value={editorContent}
                onChange={(value) => {
                  setEditorContent(value ?? '');
                  setDirty(value !== fileData?.content);
                }}
                theme="vs"
                options={{
                  fontSize: 13,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
              />
            )}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            Select a file to view or edit.
          </div>
        )}
      </div>

      {/* New Folder Dialog */}
      {showNewFolderDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-base font-semibold">
                <FolderPlus className="h-4 w-4" /> New Folder
              </h2>
              <button
                onClick={() => setShowNewFolderDialog(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="mb-3 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
              Location: <code className="font-mono">{workdir}/</code>
            </div>
            <form onSubmit={handleNewFolderSubmit} className="space-y-3">
              <div>
                <input
                  className="input"
                  value={newFolderName}
                  onChange={(e) => {
                    setNewFolderName(e.target.value);
                    setNewFolderError(null);
                  }}
                  placeholder="folder-name"
                  autoFocus
                  required
                />
                {newFolderError && (
                  <p className="mt-1 text-xs text-destructive">{newFolderError}</p>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowNewFolderDialog(false)}
                  className="btn-outline"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={newFolderMutation.isPending}
                >
                  {newFolderMutation.isPending ? 'Creating…' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Upload Dialog */}
      {showUploadDialog && pendingFile && (
        <UploadDialog
          file={pendingFile}
          connectionId={connectionId}
          sandboxId={sandboxId}
          workdir={workdir}
          isUploading={uploadMutation.isPending}
          error={uploadMutation.error instanceof Error ? uploadMutation.error.message : null}
          onConfirm={(destPath) => {
            uploadMutation.mutate({ file: pendingFile, destPath });
          }}
          onCancel={() => {
            setShowUploadDialog(false);
            setPendingFile(null);
          }}
        />
      )}
    </div>
  );
}


// --- Upload Dialog: lets user select a target folder ---
function UploadDialog({
  file,
  connectionId,
  sandboxId,
  workdir,
  isUploading,
  error,
  onConfirm,
  onCancel,
}: {
  file: File;
  connectionId: string;
  sandboxId: string;
  workdir: string;
  isUploading: boolean;
  error: string | null;
  onConfirm: (destPath: string) => void;
  onCancel: () => void;
}) {
  const [selectedDir, setSelectedDir] = useState(workdir);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Upload className="h-4 w-4" /> Upload File
          </h2>
          <button onClick={onCancel} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-3 rounded-md bg-muted/50 px-3 py-2 text-sm">
          <span className="text-muted-foreground">File: </span>
          <span className="font-medium">{file.name}</span>
          <span className="ml-2 text-xs text-muted-foreground">
            ({(file.size / 1024).toFixed(1)} KB)
          </span>
        </div>

        <div className="mb-2 text-sm font-medium">Destination folder:</div>
        <FolderPicker
          connectionId={connectionId}
          sandboxId={sandboxId}
          workdir={workdir}
          selectedDir={selectedDir}
          onSelect={setSelectedDir}
        />

        <div className="mt-3 rounded-md bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          Target: <code className="font-mono">{selectedDir}/{file.name}</code>
        </div>

        {error && (
          <div className="mt-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="btn-outline">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(selectedDir === '/' ? `/${file.name}` : `${selectedDir}/${file.name}`)}
            className="btn-primary"
            disabled={isUploading}
          >
            {isUploading ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  );
}


// --- FolderPicker: browse workspace and select a directory ---
function FolderPicker({
  connectionId,
  sandboxId,
  workdir,
  selectedDir,
  onSelect,
}: {
  connectionId: string;
  sandboxId: string;
  workdir: string;
  selectedDir: string;
  onSelect: (dir: string) => void;
}) {
  const [browsingDir, setBrowsingDir] = useState(workdir);

  const { data } = useQuery({
    queryKey: ['files', connectionId, sandboxId, browsingDir],
    queryFn: () =>
      api.get<{ path: string; entries: FileEntry[] }>(
        `/connections/${connectionId}/sandboxes/${sandboxId}/files?path=${encodeURIComponent(browsingDir)}`,
      ),
    staleTime: 10_000,
  });

  const dirs = useMemo(
    () => (data?.entries ?? []).filter((e) => e.kind === 'directory'),
    [data],
  );

  // Breadcrumb path segments for navigation.
  const segments = browsingDir.replace(/^\//, '').split('/').filter(Boolean);
  // Root label: show '/' when workdir is root, otherwise the last segment.
  const rootLabel = workdir === '/' ? '/' : (workdir.split('/').pop() || '/');
  // Build cumulative paths for breadcrumbs.
  const breadcrumbs: { label: string; path: string }[] = [];
  let acc = '';
  for (const seg of segments) {
    acc += '/' + seg;
    breadcrumbs.push({ label: seg, path: acc });
  }

  return (
    <div className="max-h-48 overflow-auto rounded-md border">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 border-b bg-muted/30 px-2 py-1 text-xs">
        <button
          onClick={() => {
            setBrowsingDir(workdir);
            onSelect(workdir);
          }}
          className="text-primary hover:underline"
        >
          {rootLabel}
        </button>
        {breadcrumbs.map((bc) => (
          <span key={bc.path} className="flex items-center gap-1">
            <span className="text-muted-foreground">/</span>
            <button
              onClick={() => {
                setBrowsingDir(bc.path);
                onSelect(bc.path);
              }}
              className="text-primary hover:underline"
            >
              {bc.label}
            </button>
          </span>
        ))}
      </div>

      {/* Current selection indicator */}
      <button
        onClick={() => onSelect(browsingDir)}
        className={cn(
          'flex w-full items-center gap-2 border-b px-3 py-1.5 text-sm transition-colors',
          selectedDir === browsingDir
            ? 'bg-primary/10 text-primary font-medium'
            : 'hover:bg-accent',
        )}
      >
        <FolderOpen className="h-3.5 w-3.5 shrink-0" />
        <span>. (current directory)</span>
      </button>

      {/* Subdirectories */}
      {dirs.length === 0 ? (
        <div className="px-3 py-2 text-xs text-muted-foreground">No subdirectories</div>
      ) : (
        dirs.map((dir) => {
          const dirName = dir.path.split('/').pop() ?? dir.path;
          const isSelected = selectedDir === dir.path;
          return (
            <div key={dir.path} className="flex items-center">
              <button
                onClick={() => onSelect(dir.path)}
                className={cn(
                  'flex flex-1 items-center gap-2 px-3 py-1.5 text-sm transition-colors',
                  isSelected
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'hover:bg-accent',
                )}
              >
                <Folder className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                <span className="truncate">{dirName}</span>
              </button>
              <button
                onClick={() => setBrowsingDir(dir.path)}
                className="px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground"
                title="Open"
              >
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}


// --- FileTree component ---
function FileTree({
  connectionId,
  sandboxId,
  path,
  level,
  selectedPath,
  onSelect,
}: {
  connectionId: string;
  sandboxId: string;
  path: string;
  level: number;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const { data } = useQuery({
    queryKey: ['files', connectionId, sandboxId, path],
    queryFn: () =>
      api.get<{ path: string; entries: FileEntry[] }>(
        `/connections/${connectionId}/sandboxes/${sandboxId}/files?path=${encodeURIComponent(path)}`,
      ),
    staleTime: 10_000,
  });

  const toggle = (dir: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(dir)) next.delete(dir);
      else next.add(dir);
      return next;
    });
  };

  const entries = data?.entries ?? [];

  return (
    <div className="space-y-0.5">
      {entries.map((entry) => {
        const isDir = entry.kind === 'directory';
        const isOpen = expanded.has(entry.path);
        return (
          <div key={entry.path}>
            <button
              onClick={() => (isDir ? toggle(entry.path) : onSelect(entry.path))}
              className={cn(
                'flex w-full items-center gap-1 rounded px-1 py-0.5 text-sm hover:bg-accent',
                selectedPath === entry.path && 'bg-secondary',
              )}
              style={{ paddingLeft: `${level * 12 + 4}px` }}
            >
              {isDir ? (
                <>
                  {isOpen ? (
                    <ChevronDown className="h-3 w-3 shrink-0" />
                  ) : (
                    <ChevronRight className="h-3 w-3 shrink-0" />
                  )}
                  <Folder className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                </>
              ) : (
                <>
                  <span className="w-3" />
                  <FileIcon className="h-3.5 w-3.5 shrink-0 text-gray-500" />
                </>
              )}
              <span className="truncate">{entry.path.split('/').pop()}</span>
            </button>
            {isDir && isOpen && (
              <FileTree
                connectionId={connectionId}
                sandboxId={sandboxId}
                path={entry.path}
                level={level + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function detectLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase();
  const map: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    jsx: 'javascript',
    tsx: 'typescript',
    json: 'json',
    md: 'markdown',
    yml: 'yaml',
    yaml: 'yaml',
    sh: 'shell',
    html: 'html',
    css: 'css',
    txt: 'plaintext',
  };
  return map[ext ?? ''] ?? 'plaintext';
}

// Re-export type for SandboxDetailPage
export type { FileWriteResult } from '@/lib/api';
