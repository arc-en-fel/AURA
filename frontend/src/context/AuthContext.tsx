import React, { createContext, useContext, useEffect, useState } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { supabase, isSupabaseConfigured } from '@/services/supabase';
import { getUseMockMode, setUseMockMode } from '@/services/api';

interface AuthContextType {
  user: User | null;
  session: Session | null;
  isLoading: boolean;
  isConfigured: boolean;
  isMockMode: boolean;
  signIn: (email: string, password: string) => Promise<{ error?: string }>;
  signUp: (email: string, password: string) => Promise<{ error?: string; message?: string }>;
  signInWithOAuth: (provider: 'google' | 'github') => Promise<{ error?: string }>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ error?: string; message?: string }>;
  loginAsDemoUser: () => void;
  toggleMockMode: (enabled: boolean) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Production authentication strictly requires valid Supabase session

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isMockMode, setIsMockModeState] = useState<boolean>(getUseMockMode());

  useEffect(() => {
    if (isSupabaseConfigured) {
      // Live authentication configured: do NOT auto-activate demo session
      // Initialize real Supabase session
      supabase.auth.getSession().then(({ data: { session } }) => {
        setSession(session);
        setUser(session?.user ?? null);
        if (session) {
          localStorage.removeItem('aura_demo_session');
          setUseMockMode(false);
          setIsMockModeState(false);
        }
        setIsLoading(false);
      }).catch(() => {
        setIsLoading(false);
      });

      // Subscribe to auth state changes
      const { data: { subscription } } = supabase.auth.onAuthStateChange(
        (_event, session) => {
          setSession(session);
          setUser(session?.user ?? null);
          if (session) {
            localStorage.removeItem('aura_demo_session');
            setUseMockMode(false);
            setIsMockModeState(false);
          }
          setIsLoading(false);
        }
      );

      return () => {
        subscription.unsubscribe();
      };
    } else {
      // Credentials not configured; require user to provide configuration
      setUser(null);
      setSession(null);
      setIsLoading(false);
    }
  }, []);

  const signIn = async (email: string, password: string) => {
    if (!isSupabaseConfigured) {
      return { error: 'Supabase credentials are not configured in environment. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env.' };
    }
    const { error, data } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      return { error: error.message };
    }
    if (data.session) {
      localStorage.removeItem('aura_demo_session');
      setUseMockMode(false);
      setIsMockModeState(false);
    }
    return {};
  };

  const signUp = async (email: string, password: string) => {
    if (!isSupabaseConfigured) {
      return { error: 'Supabase credentials are not configured in environment. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env.' };
    }
    const { error, data } = await supabase.auth.signUp({ email, password });
    if (error) {
      return { error: error.message };
    }
    if (data.user && !data.session) {
      return { message: 'Registration successful! Please check your email to confirm your account.' };
    }
    return {};
  };

  const signOut = async () => {
    localStorage.removeItem('aura_demo_session');
    localStorage.removeItem('aura_selected_crm_id');
    setUseMockMode(false);
    setIsMockModeState(false);
    if (isSupabaseConfigured) {
      await supabase.auth.signOut();
    }
    setUser(null);
    setSession(null);
  };

  const resetPassword = async (email: string) => {
    if (!isSupabaseConfigured) {
      return { error: 'Supabase credentials are not configured in environment. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env.' };
    }
    const { error } = await supabase.auth.resetPasswordForEmail(email);
    if (error) {
      return { error: error.message };
    }
    return { message: 'Password reset link sent to your email.' };
  };

  const signInWithOAuth = async (provider: 'google' | 'github'): Promise<{ error?: string }> => {
    if (!isSupabaseConfigured) {
      return { error: 'Supabase authentication is not configured in environment.' };
    }
    try {
      const callbackUrl = `${window.location.origin}/auth/callback`;
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: callbackUrl,
        },
      });

      if (error) {
        return { error: error.message };
      }

      if (data?.url) {
        // Pre-flight check to verify if the provider is enabled before leaving SPA
        try {
          const probe = await fetch(data.url, { method: 'GET' });
          if (probe.status === 400) {
            const body = await probe.json().catch(() => null);
            const msg = body?.msg || body?.message || 'Unsupported provider: provider is not enabled';
            return {
              error: `${provider === 'google' ? 'Google' : 'GitHub'} OAuth not configured: ${msg}. Provider credentials must be enabled in the Supabase Dashboard.`,
            };
          }
        } catch {
          // If cross-origin redirect throws, provider is active and redirecting
        }

        window.location.href = data.url;
        return {};
      }

      return { error: 'Failed to generate OAuth authorization URL.' };
    } catch (err: any) {
      return { error: err.message || 'OAuth sign-in failed.' };
    }
  };

  const loginAsDemoUser = () => {
    // Disabled in production
  };

  const toggleMockMode = (enabled: boolean) => {
    setUseMockMode(enabled);
    setIsMockModeState(enabled);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        isLoading,
        isConfigured: isSupabaseConfigured,
        isMockMode,
        signIn,
        signUp,
        signInWithOAuth,
        signOut,
        resetPassword,
        loginAsDemoUser,
        toggleMockMode,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
