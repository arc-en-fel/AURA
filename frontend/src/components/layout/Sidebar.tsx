import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderKanban,
  Database,
  GitBranch,
  BarChart3,
  Dna,
  Settings,
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
}

export const Sidebar: React.FC<SidebarProps> = ({ isMobileOpen, onCloseMobile }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isAIOpen, setIsAIOpen] = useState(false);
  const { activeCRM } = useCRM();

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'My CRMs', path: '/crms', icon: FolderKanban },
    { name: 'Build a CRM', path: '/chat-crm', icon: MessageCircle, highlight: true },
    { name: 'Records', path: '/records', icon: Database },
    { name: 'Workflows', path: '/workflows', icon: GitBranch },
    { name: 'Analytics', path: '/analytics', icon: BarChart3 },
    { name: 'Evolution Center', path: '/evolution', icon: Dna, badge: 'Core' },
    { name: 'Settings', path: '/settings', icon: Settings },
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
        className={`fixed top-0 bottom-0 left-0 z-40 bg-aura-navy text-white transition-all duration-300 flex flex-col justify-between border-r border-slate-800 shadow-xl
          ${isMobileOpen ? 'translate-x-0 w-64' : '-translate-x-full lg:translate-x-0'}
          ${isCollapsed ? 'lg:w-20' : 'lg:w-64'}
        `}
      >
        {/* Top: Logo & Brand */}
        <div>
          <div className="flex items-center justify-between px-5 py-5 border-b border-white/10">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-aura-deep to-aura-cyan flex items-center justify-center text-white font-extrabold shadow-glow-cyan shrink-0">
                <Layers className="w-5 h-5 text-white" />
              </div>
              {!isCollapsed && (
                <div className="flex flex-col truncate">
                  <span className="font-extrabold text-base tracking-wider text-white">
                    AURA
                  </span>
                  <span className="text-[10px] text-aura-cyan font-medium tracking-widest uppercase">
                    Self-Evolving CRM
                  </span>
                </div>
              )}
            </div>

            {/* Desktop collapse toggle */}
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="hidden lg:flex p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {isCollapsed ? (
                <ChevronRight className="w-4 h-4" />
              ) : (
                <ChevronLeft className="w-4 h-4" />
              )}
            </button>
          </div>

          {/* Active CRM context pill */}
          {!isCollapsed && activeCRM && (
            <div className="mx-4 mt-4 p-2.5 rounded-xl bg-aura-deep/60 border border-white/10 flex items-center justify-between">
              <div className="truncate pr-2">
                <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                  Active CRM
                </p>
                <p className="text-xs font-semibold text-white truncate">
                  {activeCRM.name}
                </p>
              </div>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-aura-cyan/20 text-aura-cyan shrink-0">
                v{activeCRM.configuration_version}
              </span>
            </div>
          )}

          {/* Navigation Links */}
          <nav className="mt-4 px-3 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={onCloseMobile}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all group ${
                      isActive
                        ? 'bg-aura-cyan text-aura-navy font-bold shadow-sm'
                        : item.highlight
                        ? 'text-aura-yellow hover:bg-white/5 hover:text-yellow-300'
                        : 'text-slate-300 hover:bg-white/10 hover:text-white'
                    } ${isCollapsed ? 'justify-center px-0' : ''}`
                  }
                  title={isCollapsed ? item.name : undefined}
                >
                  <Icon
                    className={`w-4 h-4 shrink-0 transition-colors ${
                      item.highlight ? 'text-aura-yellow' : ''
                    }`}
                  />
                  {!isCollapsed && <span className="truncate">{item.name}</span>}
                  {!isCollapsed && item.badge && (
                    <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded-full font-bold bg-aura-yellow text-aura-navy uppercase tracking-wider">
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Bottom Area: AI Assistant Floating/Docked Trigger */}
        <div className="p-3 border-t border-white/10 space-y-2">
          {/* AI Assistant Button in Sidebar */}
          <button
            onClick={() => setIsAIOpen(true)}
            className={`w-full flex items-center gap-2.5 p-2.5 rounded-xl bg-gradient-to-r from-aura-deep to-aura-navy hover:from-aura-cyan hover:to-aura-deep text-white border border-aura-cyan/30 shadow-subtle hover:shadow-glow-cyan transition-all group ${
              isCollapsed ? 'justify-center p-2.5' : 'justify-between'
            }`}
            title="AURA AI Assistant Copilot"
          >
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-aura-cyan/20 flex items-center justify-center text-aura-cyan group-hover:text-white transition-colors shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              {!isCollapsed && (
                <div className="text-left">
                  <p className="text-xs font-bold leading-tight">AI Copilot</p>
                  <p className="text-[10px] text-slate-300">CRM Intelligence</p>
                </div>
              )}
            </div>
            {!isCollapsed && (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-aura-cyan opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-aura-cyan"></span>
              </span>
            )}
          </button>
        </div>
      </aside>

      {/* Floating AI Assistant Trigger Button (Visible everywhere for instant access) */}
      <button
        onClick={() => setIsAIOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-full bg-aura-navy text-white hover:bg-aura-deep border-2 border-aura-cyan shadow-elevated hover:shadow-glow-cyan transition-all active:scale-95 group"
        title="Open AURA AI Assistant"
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
