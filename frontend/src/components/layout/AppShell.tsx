import { useEffect } from 'react';
import { Outlet, useNavigate, useLocation, Link } from 'react-router-dom';
import { Boxes, Server, LogOut, Terminal, ChevronRight, Shield } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';

const navItems = [
  { path: '/sandboxes', label: 'Sandboxes', icon: Boxes },
  { path: '/connections', label: 'Connections', icon: Server },
  { path: '/policies', label: '权限管理', icon: Shield },
];

export function AppShell() {
  const { isAuthenticated, actor, fetchMe, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!isAuthenticated) {
      fetchMe().catch(() => {
        navigate('/login', { replace: true });
      });
    }
  }, [isAuthenticated, fetchMe, navigate]);

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-muted-foreground">Checking authentication…</div>
      </div>
    );
  }

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  // Detect if we're inside a sandbox detail page: /sandboxes/:connectionId/:sandboxId
  const pathParts = location.pathname.split('/').filter(Boolean);
  const inSandboxDetail =
    pathParts[0] === 'sandboxes' && pathParts.length >= 3;
  const currentSandboxId = inSandboxDetail ? pathParts[2] : null;
  const currentConnectionId = inSandboxDetail ? pathParts[1] : null;

  return (
    <div className="flex h-screen flex-col">
      {/* TopBar */}
      <header className="flex h-12 items-center justify-between border-b px-4">
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5" />
          <span className="font-semibold">Sandbox Console</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">{actor?.actor_id ?? 'admin'}</span>
          <button
            onClick={handleLogout}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="flex w-52 flex-col border-r p-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = location.pathname.startsWith(item.path);
            return (
              <div key={item.path}>
                <Link
                  to={item.path}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    active
                      ? 'bg-secondary text-secondary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>

                {/* Sandbox context sub-navigation */}
                {item.path === '/sandboxes' && inSandboxDetail && currentSandboxId && (
                  <div className="ml-4 mt-0.5 border-l pl-2">
                    <Link
                      to={`/sandboxes/${currentConnectionId}/${currentSandboxId}?tab=overview`}
                      className={cn(
                        'flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-mono text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
                        'text-foreground',
                      )}
                    >
                      <ChevronRight className="h-3 w-3 shrink-0" />
                      <span className="truncate">{currentSandboxId}</span>
                    </Link>
                  </div>
                )}
              </div>
            );
          })}
        </aside>

        {/* Main Content */}
        <main className={cn('flex-1 overflow-auto', !inSandboxDetail && 'p-6 h-full')}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
