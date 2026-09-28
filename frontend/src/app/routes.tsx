import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { LoginPage } from '@/pages/LoginPage';
import { ConnectionsPage } from '@/pages/ConnectionsPage';
import { SandboxesPage } from '@/pages/SandboxesPage';
import { SandboxDetailPage } from '@/pages/SandboxDetailPage';
import { PoliciesPage } from '@/pages/PoliciesPage';
import { DashboardPage } from '@/pages/DashboardPage';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <AppShell />,
    errorElement: (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="text-muted-foreground">
          The page or resource could not be found.{' '}
          <a href="/sandboxes" className="text-primary underline">Go to Sandboxes</a>
        </p>
      </div>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'connections', element: <ConnectionsPage /> },
      { path: 'sandboxes', element: <SandboxesPage /> },
      {
        path: 'sandboxes/:connectionId/:sandboxId',
        element: <SandboxDetailPage />,
      },
      { path: 'policies', element: <PoliciesPage /> },
      // Catch-all: redirect any unknown URL to sandboxes.
      { path: '*', element: <Navigate to="/sandboxes" replace /> },
    ],
  },
]);
