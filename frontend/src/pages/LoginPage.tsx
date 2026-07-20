import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Terminal, Lock } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';

export function LoginPage() {
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError('Please enter the admin token');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await login(token);
      navigate('/sandboxes', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary/30">
      <div className="w-full max-w-md rounded-lg border bg-background p-8 shadow-lg">
        <div className="mb-6 flex items-center gap-2">
          <Terminal className="h-6 w-6" />
          <h1 className="text-xl font-semibold">Sandbox Explorer</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium">Admin Token</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                className="input pl-9"
                placeholder="Enter admin token"
                disabled={loading}
                autoFocus
              />
            </div>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-muted-foreground">
          Set <code className="rounded bg-muted px-1 py-0.5">EXPLORER_ADMIN_TOKEN</code> env var on the server.
        </p>
      </div>
    </div>
  );
}
