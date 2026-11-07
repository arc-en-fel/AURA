import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderKanban,
  Database,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Bot,
  Layers,
  MessageCircle,
  Sparkles,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { AIAssistantDrawer } from '@/features/ai-assistant/AIAssistantDrawer';

export interface SidebarProps {
  isMobileOpen: boolean;
  onCloseMobile: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isMobileOpen,
  onCloseMobile,
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const [isAIOpen, setIsAIOpen] = useState(false);
  const { activeCRM } = useCRM();

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'My CRMs', path: '/crms', icon: FolderKanban },
    { name: 'Build a CRM', path: '/chat-crm', icon: MessageCircle, highlight: true },
    { name: 'Records', path: '/records', icon: Database },
    { name: 'Analytics', path: '/analytics', icon: BarChart3 },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-xs lg:hidden"
          onClick={onCloseMobile}
        />
      )}

      {/* Main Sidebar */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-40 bg-aura-navy text-white transition-all duration-300 flex flex-col justify-between border-r border-slate-800 shadow-xl overflow-x-hidden
          ${isMobileOpen ? 'translate-x-0 w-64' : '-translate-x-full lg:translate-x-0'}
          ${isCollapsed ? 'lg:w-20' : 'lg:w-64'}
        `}
      >
        {/* Top: Logo & Brand + Navigation */}
        <div className="flex flex-col min-w-0">
          {/* Header Brand Region */}
          {isCollapsed ? (
            <div className="flex flex-col items-center justify-center py-4 px-2 border-b border-white/10 h-22 gap-2 shrink-0">
              <div
                className="w-9 h-9 rounded-xl bg-gradient-to-tr from-aura-deep to-aura-cyan flex items-center justify-center text-white font-extrabold shadow-glow-cyan shrink-0"
                title="AURA Self-Evolving CRM"
                aria-label="AURA Logo"
              >
                <Layers className="w-5 h-5 text-white" />
              </div>
              {onToggleCollapse && (
                <button
                  onClick={onToggleCollapse}
                  className="hidden lg:flex p-1 rounded-md text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  title="Expand sidebar"
                  aria-label="Expand sidebar"
                >
                  <ChevronRight className="w-3.5 h-3.5 text-aura-cyan" />
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-between px-4 py-4 border-b border-white/10 h-16 shrink-0">
              <div className="flex items-center gap-3 overflow-hidden">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-aura-deep to-aura-cyan flex items-center justify-center text-white font-extrabold shadow-glow-cyan shrink-0">
                  <Layers className="w-5 h-5 text-white" />
                </div>
                <div className="flex flex-col truncate">
                  <span className="font-extrabold text-base tracking-wider text-white">
                    AURA
                  </span>
                  <span className="text-[10px] text-aura-cyan font-medium tracking-widest uppercase">
                    Self-Evolving CRM
                  </span>
                </div>
              </div>

              {/* Desktop collapse toggle */}
              {onToggleCollapse && (
                <button
                  onClick={onToggleCollapse}
                  className="hidden lg:flex p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors shrink-0"
                  title="Collapse sidebar"
                  aria-label="Collapse sidebar"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
              )}
            </div>
          )}

          {/* Active CRM Context Indicator */}
          {activeCRM && (
            isCollapsed ? (
              <div className="flex justify-center px-2 pt-3 pb-1 border-b border-white/5">
                <div
                  className="w-10 h-10 rounded-xl bg-aura-deep/60 border border-white/10 flex flex-col items-center justify-center text-center cursor-default group"
                  title={`Selected Workspace: ${activeCRM.name} (v${activeCRM.configuration_version})`}
                  aria-label={`Selected Workspace: ${activeCRM.name}`}
                >
                  <span className="text-[10px] font-bold text-aura-cyan uppercase">
                    {activeCRM.name.slice(0, 2).toUpperCase()}
                  </span>
                  <span className="text-[8px] text-slate-400 font-mono leading-none">
                    v{activeCRM.configuration_version}
                  </span>
                </div>
              </div>
            ) : (
              <div className="mx-4 mt-3 p-2.5 rounded-xl bg-aura-deep/60 border border-white/10 flex items-center justify-between">
                <div className="truncate pr-2">
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Selected Workspace
                  </p>
                  <p className="text-xs font-semibold text-white truncate">
                    {activeCRM.name}
                  </p>
                </div>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-aura-cyan/20 text-aura-cyan shrink-0">
                  v{activeCRM.configuration_version}
                </span>
              </div>
            )
          )}

          {/* Navigation Links */}
          <nav className={`mt-3 space-y-1.5 ${isCollapsed ? 'px-2' : 'px-3'}`}>
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={onCloseMobile}
                  className={({ isActive }) =>
                    `flex items-center rounded-xl text-xs font-medium transition-all group ${
                      isCollapsed
                        ? 'justify-center w-10 h-10 mx-auto'
                        : 'gap-3 px-3 py-2.5'
                    } ${
                      isActive
                        ? 'bg-aura-cyan text-aura-navy font-bold shadow-sm'
                        : item.highlight
                        ? 'text-aura-yellow hover:bg-white/5 hover:text-yellow-300'
                        : 'text-slate-300 hover:bg-white/10 hover:text-white'
                    }`
                  }
                  title={isCollapsed ? item.name : undefined}
                  aria-label={item.name}
                >
                  <Icon
                    className={`w-4 h-4 shrink-0 transition-colors ${
                      item.highlight ? 'text-aura-yellow' : ''
                    }`}
                  />
                  {!isCollapsed && <span className="truncate">{item.name}</span>}
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Bottom Area: AI Assistant Copilot Trigger */}
        <div className={`p-3 border-t border-white/10 ${isCollapsed ? 'flex justify-center' : ''}`}>
          <button
            onClick={() => setIsAIOpen(true)}
            className={`flex items-center rounded-xl bg-gradient-to-r from-aura-deep to-aura-navy hover:from-aura-cyan hover:to-aura-deep text-white border border-aura-cyan/30 shadow-subtle hover:shadow-glow-cyan transition-all group ${
              isCollapsed
                ? 'w-10 h-10 justify-center p-0'
                : 'w-full justify-between p-2.5'
            }`}
            title="AURA AI Assistant Copilot"
            aria-label="Open AURA AI Copilot"
          >
            {isCollapsed ? (
              <div className="w-7 h-7 rounded-lg bg-aura-cyan/20 flex items-center justify-center text-aura-cyan group-hover:text-white transition-colors">
                <Bot className="w-4 h-4" />
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-aura-cyan/20 flex items-center justify-center text-aura-cyan group-hover:text-white transition-colors shrink-0">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div className="text-left">
                    <p className="text-xs font-bold leading-tight">AI Copilot</p>
                    <p className="text-[10px] text-slate-300">CRM Intelligence</p>
                  </div>
                </div>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-aura-cyan opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-aura-cyan"></span>
                </span>
              </>
            )}
          </button>
        </div>
      </aside>

      {/* Floating AI Assistant Trigger Button (Visible everywhere for instant access) */}
      <button
        onClick={() => setIsAIOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-full bg-aura-navy text-white hover:bg-aura-deep border-2 border-aura-cyan shadow-elevated hover:shadow-glow-cyan transition-all active:scale-95 group"
        title="Open AURA AI Assistant"
        aria-label="Open AURA AI Assistant"
      >
        <Sparkles className="w-5 h-5 text-aura-cyan animate-pulse-subtle" />
        <span className="text-xs font-bold tracking-wide">AURA Copilot</span>
        <span className="w-2 h-2 rounded-full bg-emerald-400" />
      </button>

      {/* Slide-over Assistant Drawer */}
      <AIAssistantDrawer isOpen={isAIOpen} onClose={() => setIsAIOpen(false)} />
    </>
  );
};
