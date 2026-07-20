import { useState, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Play, Copy, RotateCcw } from 'lucide-react';
import { api, type CommandCreateResponse } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';

interface CommandsTabProps {
  connectionId: string;
  sandboxId: string;
  workdir: string;
}

interface OutputChunk {
  stream: 'stdout' | 'stderr';
  data: string;
}

interface CommandResult {
  exitCode: number | null;
  durationMs: number | null;
  status: string;
}

export function CommandsTab({ connectionId, sandboxId, workdir }: CommandsTabProps) {
  const [command, setCommand] = useState('');
  const [cwd, setCwd] = useState(workdir);
  const [timeout, setTimeout] = useState(300);
  const [outputs, setOutputs] = useState<OutputChunk[]>([]);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [running, setRunning] = useState(false);
  const outputRef = useRef<HTMLDivElement>(null);
  const sessionToken = useAuthStore((s) => s.sessionToken);

  const runMutation = useMutation({
    mutationFn: (cmd: string) =>
      api.post<CommandCreateResponse>(
        `/connections/${connectionId}/sandboxes/${sandboxId}/commands`,
        { command: cmd, cwd, timeout_seconds: timeout, mode: 'foreground' },
      ),
  });

  const runCommand = async () => {
    if (!command.trim()) return;

    setOutputs([]);
    setResult(null);
    setRunning(true);

    try {
      // 1. POST to create the command.
      const resp = await runMutation.mutateAsync(command);

      // 2. Consume SSE stream with fetch (to send Authorization header).
      const sseUrl = `/api/v1/connections/${connectionId}/sandboxes/${sandboxId}/commands/${resp.command_id}/stream`;
      const response = await fetch(sseUrl, {
        headers: {
          Authorization: `Bearer ${sessionToken}`,
        },
      });

      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'output') {
                setOutputs((prev) => [
                  ...prev,
                  { stream: event.stream, data: event.data },
                ]);
                // Auto-scroll.
                requestAnimationFrame(() => {
                  if (outputRef.current) {
                    outputRef.current.scrollTop = outputRef.current.scrollHeight;
                  }
                });
              } else if (event.type === 'finished') {
                setResult({
                  exitCode: event.exit_code,
                  durationMs: event.duration_ms,
                  status: event.status,
                });
              } else if (event.type === 'timeout') {
                setResult({
                  exitCode: null,
                  durationMs: event.duration_ms,
                  status: 'timeout',
                });
              }
            } catch {
              // Ignore malformed events.
            }
          }
        }
      }
    } catch (err) {
      setOutputs((prev) => [
        ...prev,
        { stream: 'stderr', data: `Error: ${err instanceof Error ? err.message : 'Unknown'}\n` },
      ]);
    } finally {
      setRunning(false);
    }
  };

  const copyOutput = () => {
    const text = outputs.map((o) => o.data).join('');
    navigator.clipboard.writeText(text);
  };

  const rerun = () => {
    runCommand();
  };

  const stdout = outputs.filter((o) => o.stream === 'stdout').map((o) => o.data).join('');
  const stderr = outputs.filter((o) => o.stream === 'stderr').map((o) => o.data).join('');

  return (
    <div className="flex h-full flex-col p-4">
      {/* Command input */}
      <div className="space-y-2 border-b pb-4">
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-muted-foreground">Command</label>
            <input
              className="input font-mono"
              placeholder="e.g. echo hello"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !running) runCommand();
              }}
              disabled={running}
            />
          </div>
          <div className="w-40">
            <label className="mb-1 block text-xs text-muted-foreground">Working Dir</label>
            <input
              className="input font-mono text-xs"
              value={cwd}
              onChange={(e) => setCwd(e.target.value)}
              disabled={running}
            />
          </div>
          <div className="w-20">
            <label className="mb-1 block text-xs text-muted-foreground">Timeout (s)</label>
            <input
              className="input"
              type="number"
              value={timeout}
              onChange={(e) => setTimeout(Number(e.target.value))}
              disabled={running}
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={runCommand}
              disabled={running || !command.trim()}
              className="btn-primary"
            >
              <Play className="h-4 w-4" />
              {running ? 'Running…' : 'Run'}
            </button>
          </div>
        </div>

        {/* Status bar */}
        {result && (
          <div className="flex items-center gap-4 text-sm">
            <span className={cn(
              'badge',
              result.status === 'succeeded' ? 'border-green-300 bg-green-100 text-green-700'
                : result.status === 'failed' ? 'border-red-300 bg-red-100 text-red-700'
                : 'border-yellow-300 bg-yellow-100 text-yellow-700',
            )}>
              {result.status}
            </span>
            {result.exitCode !== null && (
              <span className="text-muted-foreground">Exit: {result.exitCode}</span>
            )}
            {result.durationMs !== null && (
              <span className="text-muted-foreground">{result.durationMs}ms</span>
            )}
            <div className="flex-1" />
            <button onClick={copyOutput} className="btn-outline btn-sm">
              <Copy className="h-3 w-3" /> Copy
            </button>
            <button onClick={rerun} className="btn-outline btn-sm" disabled={running}>
              <RotateCcw className="h-3 w-3" /> Re-run
            </button>
          </div>
        )}
      </div>

      {/* Output */}
      <div className="flex-1 overflow-auto" ref={outputRef}>
        {outputs.length === 0 && !running ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            Run a command to see output.
          </div>
        ) : (
          <div className="space-y-2 p-2">
            {stdout && (
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">stdout</div>
                <pre className="whitespace-pre-wrap rounded bg-gray-50 p-3 font-mono text-xs dark:bg-gray-900">
                  {stdout}
                </pre>
              </div>
            )}
            {stderr && (
              <div>
                <div className="mb-1 text-xs font-medium text-red-600">stderr</div>
                <pre className="whitespace-pre-wrap rounded bg-red-50 p-3 font-mono text-xs text-red-900 dark:bg-red-950">
                  {stderr}
                </pre>
              </div>
            )}
            {running && (
              <div className="text-sm text-muted-foreground">● running…</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
