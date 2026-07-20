import { useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { api, type TerminalCreateResponse } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';

interface TerminalTabProps {
  connectionId: string;
  sandboxId: string;
}

export function TerminalTab({ connectionId, sandboxId }: TerminalTabProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerm | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionToken = useAuthStore((s) => s.sessionToken);

  useEffect(() => {
    let disposed = false;

    async function init() {
      if (!containerRef.current) return;

      const resp = await api.post<TerminalCreateResponse>(
        `/connections/${connectionId}/sandboxes/${sandboxId}/terminals`,
      );
      if (disposed) return;

      const term = new XTerm({
        fontSize: 13,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        theme: { background: '#1e1e1e', foreground: '#d4d4d4' },
        cursorBlink: true,
        convertEol: true,
      });
      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      term.open(containerRef.current);
      fitAddon.fit();
      termRef.current = term;
      term.focus();

      // WebSocket connection
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = window.location.host;
      const wsUrl = `${wsProtocol}//${wsHost}${resp.ws_url}?token=${sessionToken ?? ''}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setError(null);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'output') {
            term.write(msg.data);
          } else if (msg.type === 'closed') {
            term.write(`\r\n[Session closed: ${msg.reason}]\r\n`);
            setConnected(false);
          } else if (msg.type === 'error') {
            term.write(`\r\n[Error: ${msg.message}]\r\n`);
            setError(msg.message);
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        setError('WebSocket connection error');
        setConnected(false);
        term.write('\r\n[WebSocket error — commands will not execute]\r\n');
      };

      ws.onclose = () => {
        setConnected(false);
      };

      // Line editing state
      let lineBuffer = '';
      let cursorPos = 0;

      const sendInput = (data: string) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'input', data }));
        }
      };

      term.onData((data) => {
        // Enter key
        if (data === '\r') {
          term.write('\r\n');
          sendInput('\r');
          lineBuffer = '';
          cursorPos = 0;
          return;
        }

        // Backspace
        if (data === '\x7f' || data === '\b') {
          if (cursorPos > 0) {
            const newPos = cursorPos - 1;
            lineBuffer = lineBuffer.slice(0, newPos) + lineBuffer.slice(cursorPos);
            cursorPos = newPos;
            term.write('\b \b');
            // Rewrite rest of line if needed
            if (cursorPos < lineBuffer.length) {
              term.write(lineBuffer.slice(cursorPos) + ' ');
              const backCount = lineBuffer.length - cursorPos + 1;
              term.write(`\x1b[${backCount}D`);
            }
          }
          return;
        }

        // Ctrl+C
        if (data === '\x03') {
          term.write('^C\r\n');
          sendInput('\x03');
          lineBuffer = '';
          cursorPos = 0;
          return;
        }

        // Ctrl+L (clear)
        if (data === '\x0c') {
          term.write('\x1b[2J\x1b[H');
          return;
        }

        // Ctrl+U (clear line)
        if (data === '\x15') {
          while (cursorPos > 0) {
            term.write('\b \b');
            cursorPos--;
          }
          lineBuffer = '';
          return;
        }

        // Regular printable character
        if (data.length === 1 && data.charCodeAt(0) >= 32) {
          lineBuffer = lineBuffer.slice(0, cursorPos) + data + lineBuffer.slice(cursorPos);
          cursorPos++;
          term.write(data);
          return;
        }

        // Other input (arrow keys etc) — send to backend
        sendInput(data);
      });

      // Handle resize
      const resizeObserver = new ResizeObserver(() => fitAddon.fit());
      resizeObserver.observe(containerRef.current);
    }

    init().catch((err) => {
      setError(err instanceof Error ? err.message : 'Failed to initialize terminal');
    });

    return () => {
      disposed = true;
      if (wsRef.current) wsRef.current.close();
      if (termRef.current) termRef.current.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId, sandboxId]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-4 py-1.5">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              connected ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span className="text-sm text-muted-foreground">
            {connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {error && <span className="text-xs text-destructive">{error}</span>}
      </div>
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden bg-[#1e1e1e] p-2"
        style={{ minHeight: '300px' }}
      />
    </div>
  );
}
