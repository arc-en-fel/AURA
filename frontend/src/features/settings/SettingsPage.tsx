import React, { useState, useEffect } from 'react';
import {
  Server,
  Shield,
  RefreshCw,
  Key,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { supabase, isSupabaseConfigured } from '@/services/supabase';

export const SettingsPage: React.FC = () => {

  const [backendHealth, setBackendHealth] = useState<'checking' | 'connected' | 'offline'>('checking');
  const [backendDetails, setBackendDetails] = useState<{
    status?: string;
    app_name?: string;
    version?: string;
    database?: string;
    auth?: string;
    error?: string;
    checkedAt?: string;
  }>({});
  const [authStatus, setAuthStatus] = useState<{
    state: 'configured' | 'missing' | 'error';
    sessionState: string;
    userEmail?: string;
  }>({
    state: isSupabaseConfigured ? 'configured' : 'missing',
    sessionState: 'Checking session...',
  });

  const checkHealth = async () => {
    setBackendHealth('checking');
    try {
      const res = await fetch('/api/v1/health');
      if (res.ok) {
        const body = await res.json();
        setBackendHealth('connected');
        setBackendDetails({
          ...body.data,
          checkedAt: new Date().toLocaleTimeString(),
        });
      } else {
        setBackendHealth('offline');
        setBackendDetails({
          error: `HTTP ${res.status}: ${res.statusText}`,
          checkedAt: new Date().toLocaleTimeString(),
        });
      }
    } catch (err: unknown) {
      setBackendHealth('offline');
      setBackendDetails({
        error: err instanceof Error ? err.message : 'Backend server unreachable at port 8000',
        checkedAt: new Date().toLocaleTimeString(),
      });
    }
  };

  useEffect(() => {
    checkHealth();
    if (isSupabaseConfigured) {
      supabase.auth.getSession().then(({ data: { session }, error }) => {
        if (error) {
          setAuthStatus({
            state: 'error',
            sessionState: `Authentication error: ${error.message}`,
          });
        } else if (session?.user) {
          setAuthStatus({
            state: 'configured',
            sessionState: 'Active Authenticated Session',
            userEmail: session.user.email || 'Authenticated User',
          });
        } else {
          setAuthStatus({
            state: 'configured',
            sessionState: 'Configured (No active user session — please log in)',
          });
        }
      }).catch((err) => {
        setAuthStatus({
          state: 'error',
          sessionState: `Failed to inspect session: ${err.message}`,
        });
      });
    } else {
      setAuthStatus({
        state: 'missing',
        sessionState: 'Missing Configuration in frontend/.env',
      });
    }
  }, []);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-xl font-bold text-aura-navy">System Settings &amp; Integration Status</h2>
        <p className="text-xs text-slate-500 mt-1">
          Inspect Supabase authentication state and backend connectivity.
        </p>
      </div>

      {/* Connectivity &amp; Service Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* FastAPI Backend Status */}
        <Card className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-aura-navy">
                <Server className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-sm text-aura-navy">FastAPI Backend</h3>
                <code className="text-[10px] text-slate-400">/api/v1/health</code>
              </div>
            </div>
            {backendHealth === 'connected' ? (
              <Badge variant="active">Connected &amp; Healthy</Badge>
            ) : backendHealth === 'checking' ? (
              <Badge variant="draft">Checking...</Badge>
            ) : (
              <Badge variant="rejected">Offline / Unreachable</Badge>
            )}
          </div>

          <p className="text-xs text-slate-500">
            Base URL: <code className="bg-slate-100 px-1.5 py-0.5 rounded font-mono text-[11px] text-aura-deep">/api/v1</code> (Proxied via Vite to port 8000).
          </p>

          {backendDetails.checkedAt && (
            <p className="text-[11px] text-slate-500">
              Last check: <span className="font-medium text-slate-700">{backendDetails.checkedAt}</span>
              {backendDetails.error && (
                <span className="block text-rose-600 mt-1">Error: {backendDetails.error}</span>
              )}
              {backendDetails.status === 'ok' && (
                <span className="block text-emerald-700 mt-1">
                  Database: {backendDetails.database} • Auth: {backendDetails.auth}
                </span>
              )}
            </p>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={checkHealth}
            leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            Recheck Backend Status
          </Button>
        </Card>

        {/* Supabase Auth Status */}
        <Card className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center text-emerald-600">
                <Shield className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-sm text-aura-navy">Supabase Authentication</h3>
                <span className="text-[10px] text-slate-400">JWT Session Verification</span>
              </div>
            </div>
            {authStatus.state === 'configured' ? (
              <Badge variant="active">Configured</Badge>
            ) : authStatus.state === 'error' ? (
              <Badge variant="rejected">Auth Error</Badge>
            ) : (
              <Badge variant="pending">Missing Config</Badge>
            )}
          </div>

          <p className="text-xs text-slate-500">
            Project URL: <code className="bg-slate-100 px-1.5 py-0.5 rounded font-mono text-[11px]">{import.meta.env.VITE_SUPABASE_URL || 'Configured via .env'}</code>
          </p>

          <div className="pt-1 flex items-center gap-2 text-xs text-slate-600">
            <Key className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <span className="truncate">
              Session: <span className="font-semibold">{authStatus.sessionState}</span>
              {authStatus.userEmail && ` (${authStatus.userEmail})`}
            </span>
          </div>
        </Card>
      </div>

      {/* Backend Integration Notice */}
      {backendHealth === 'offline' && (
        <Card className="p-4 border-amber-300 bg-amber-50/60">
          <p className="text-xs text-amber-800">
            <span className="font-bold">Notice:</span> The FastAPI backend at port 8000 is currently unreachable. Start the backend service using <code className="bg-amber-100 px-1.5 py-0.5 rounded font-mono text-[11px]">.\start-dev.bat</code>.
          </p>
        </Card>
      )}
    </div>
  );
};
