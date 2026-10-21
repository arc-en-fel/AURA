import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { CRMProvider } from '@/context/CRMContext';
import { ToastProvider } from '@/context/ToastContext';
import { ProtectedRoute } from '@/features/auth/ProtectedRoute';
import { LoginPage } from '@/features/auth/LoginPage';
import { RegisterPage } from '@/features/auth/RegisterPage';
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage';
import { AuthCallbackPage } from '@/features/auth/AuthCallbackPage';
import { AppLayout } from '@/components/layout/AppLayout';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { CRMListPage } from '@/features/crms/CRMListPage';
import { CRMDetailPage } from '@/features/crms/CRMDetailPage';
import { CRMGeneratorPage } from '@/features/crm-generator/CRMGeneratorPage';
import { CRMChatPage } from '@/features/crm-chat/CRMChatPage';
import { RecordsPage } from '@/features/records/RecordsPage';
import { WorkflowsPage } from '@/features/workflows/WorkflowsPage';
import { AnalyticsPage } from '@/features/analytics/AnalyticsPage';
import { EvolutionPage } from '@/features/evolution/EvolutionPage';
import { SettingsPage } from '@/features/settings/SettingsPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <CRMProvider>
          <ToastProvider>
            <Routes>
              {/* Public Authentication Routes */}
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/auth/callback" element={<AuthCallbackPage />} />

              {/* Protected Workspace Routes */}
              <Route element={<ProtectedRoute />}>
                <Route element={<AppLayout />}>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/crms" element={<CRMListPage />} />
                  <Route path="/crms/:crmId" element={<CRMDetailPage />} />
                  <Route path="/create-crm" element={<CRMGeneratorPage />} />
                  <Route path="/chat-crm" element={<CRMChatPage />} />
                  <Route path="/records" element={<RecordsPage />} />
                  <Route path="/workflows" element={<WorkflowsPage />} />
                  <Route path="/analytics" element={<AnalyticsPage />} />
                  <Route path="/evolution" element={<EvolutionPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Route>

              {/* Catch-all redirect */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </ToastProvider>
        </CRMProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
