import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api, type ActorInfo } from '@/lib/api';

interface AuthState {
  sessionToken: string | null;
  actor: ActorInfo | null;
  isAuthenticated: boolean;
  login: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      sessionToken: null,
      actor: { actor_id: 'admin', auth_method: 'dev' },
      isAuthenticated: true,

      login: async (adminToken: string) => {
        const result = await api.post<{
          session_token: string;
          actor_id: string;
          auth_method: string;
          expires_at: string;
        }>('/auth/login', { token: adminToken });
        set({
          sessionToken: result.session_token,
          actor: {
            actor_id: result.actor_id,
            auth_method: result.auth_method,
          },
          isAuthenticated: true,
        });
      },

      logout: async () => {
        // Auth disabled — no-op.
      },

      fetchMe: async () => {
        // Auth disabled — always authenticated.
        set({ actor: { actor_id: 'admin', auth_method: 'dev' }, isAuthenticated: true });
      },
    }),
    {
      name: 'sandbox-explorer-auth',
      partialize: (state) => ({
        sessionToken: state.sessionToken,
        actor: state.actor,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
