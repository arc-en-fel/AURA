import React, { useState } from 'react';
import { Menu, ChevronDown, LogOut, User, Server, Cpu, Check } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useCRM } from '@/context/CRMContext';
import { useLocation, useNavigate } from 'react-router-dom';

export interface NavbarProps {
  onOpenMobile: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenMobile }) => {
  const { user, signOut, isMockMode, toggleMockMode } = useAuth();
  const { crms, activeCRM, selectCRM } = useCRM();
  const location = useLocation();
  const navigate = useNavigate();
  const [showCRMDropdown, setShowCRMDropdown] = useState(false);
  const [showUserDropdown, setShowUserDropdown] = useState(false);

  // Map route to page title
  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/dashboard') return 'Dashboard';
    if (path === '/crms') return 'My CRMs';
    if (path === '/chat-crm') return 'Build a CRM';
    if (path === '/create-crm') return 'Build a CRM'; // legacy redirect safety
    if (path === '/records') return 'Dynamic Records';
    if (path === '/workflows') return 'Workflows & Automation';
    if (path === '/analytics') return 'Analytics & Funnel';
    if (path === '/evolution') return 'Evolution Center';
    if (path === '/settings') return 'Settings & Backend Status';
    if (path.startsWith('/crms/')) return 'CRM Overview';
    return 'AURA Workspace';
  };

  return (
    <header className="sticky top-0 z-30 h-16 bg-white border-b border-slate-200/80 px-4 sm:px-6 flex items-center justify-between shadow-subtle">
      {/* Left: Mobile hamburger & Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobile}
          className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 lg:hidden"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <h1 className="text-base sm:text-lg font-bold text-aura-navy leading-none">
            {getPageTitle()}
          </h1>
          <p className="text-[11px] text-slate-400 mt-1 hidden sm:block">
            {activeCRM ? `Active CRM: ${activeCRM.name}` : 'Select or generate a CRM to begin'}
          </p>
        </div>
      </div>

      {/* Right Controls: CRM Selector, Backend Status, User Account */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* CRM Selector Dropdown */}
        {crms.length > 0 && (
          <div className="relative">
            <button
              onClick={() => setShowCRMDropdown(!showCRMDropdown)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 hover:border-aura-cyan bg-slate-50 text-xs font-semibold text-aura-navy transition-colors"
            >
              <span className="w-2 h-2 rounded-full bg-aura-cyan" />
              <span className="max-w-[120px] sm:max-w-[160px] truncate">
                {activeCRM ? activeCRM.name : 'Select CRM'}
              </span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {showCRMDropdown && (
              <div
                className="absolute right-0 mt-1.5 w-60 rounded-xl bg-white shadow-elevated border border-slate-200 py-1.5 z-50 animate-fade-in"
                onClick={() => setShowCRMDropdown(false)}
              >
                <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100">
                  Switch Active CRM
                </div>
                <div className="max-h-56 overflow-y-auto">
                  {crms.map((c) => (
                    <button
                      key={c.crm_id}
                      onClick={() => selectCRM(c.crm_id)}
                      className="w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-slate-50 transition-colors"
                    >
                      <div className="truncate pr-2">
                        <p className="font-semibold text-aura-charcoal truncate">{c.name}</p>
                        <p className="text-[10px] text-slate-400">{c.configuration.industry}</p>
                      </div>
                      {activeCRM?.crm_id === c.crm_id && (
                        <Check className="w-4 h-4 text-aura-cyan shrink-0" />
                      )}
                    </button>
                  ))}
                </div>
                <div className="border-t border-slate-100 pt-1 mt-1">
                  <button
                    onClick={() => navigate('/chat-crm')}
                    className="w-full text-left px-3 py-2 text-xs font-semibold text-aura-cyan hover:bg-cyan-50 flex items-center gap-2"
                  >
                    + Build New CRM
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Backend / Mock Mode Indicator */}
        <button
          onClick={() => toggleMockMode(!isMockMode)}
          className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all ${
            isMockMode
              ? 'bg-amber-50 text-amber-700 border-amber-300 hover:bg-amber-100'
              : 'bg-emerald-50 text-emerald-700 border-emerald-300 hover:bg-emerald-100'
          }`}
          title={isMockMode ? 'Using Standalone Mock Adapter (Click to switch to Live Backend)' : 'Using Live FastAPI Backend (Click to test with Mock Adapter)'}
        >
          {isMockMode ? (
            <>
              <Cpu className="w-3.5 h-3.5 text-amber-600" />
              <span>Mock Adapter</span>
            </>
          ) : (
            <>
              <Server className="w-3.5 h-3.5 text-emerald-600" />
              <span>FastAPI Live</span>
            </>
          )}
        </button>

        {/* User Account Menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserDropdown(!showUserDropdown)}
            className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-aura-deep text-white flex items-center justify-center text-xs font-bold shadow-xs">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400 hidden sm:block" />
          </button>

          {showUserDropdown && (
            <div
              className="absolute right-0 mt-1.5 w-52 rounded-xl bg-white shadow-elevated border border-slate-200 py-1.5 z-50 animate-fade-in"
              onClick={() => setShowUserDropdown(false)}
            >
              <div className="px-3 py-2 border-b border-slate-100">
                <p className="text-xs font-bold text-aura-navy truncate">
                  {user?.user_metadata?.name || 'Authorized Operator'}
                </p>
                <p className="text-[11px] text-slate-500 truncate">{user?.email}</p>
              </div>

              <button
                onClick={() => navigate('/settings')}
                className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 flex items-center gap-2"
              >
                <User className="w-3.5 h-3.5 text-slate-400" />
                <span>Account & Backend Status</span>
              </button>

              <button
                onClick={() => signOut()}
                className="w-full text-left px-3 py-2 text-xs text-rose-600 hover:bg-rose-50 flex items-center gap-2 border-t border-slate-100"
              >
                <LogOut className="w-3.5 h-3.5 text-rose-500" />
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
