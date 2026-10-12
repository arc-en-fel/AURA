import React, { useState } from 'react';
import { Sparkles, Bot, Send, X, ArrowRight, Zap, Lightbulb } from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { useNavigate } from 'react-router-dom';

interface AIAssistantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

interface Message {
  sender: 'ai' | 'user';
  text: string;
  time: string;
  action?: { label: string; route: string };
}

export const AIAssistantDrawer: React.FC<AIAssistantDrawerProps> = ({ isOpen, onClose }) => {
  const { activeCRM } = useCRM();
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      sender: 'ai',
      text: `Hello! I am your AURA CRM Intelligence Assistant. I can help analyze your CRM architecture, recommend field adjustments, propose workflow automations, or guide evolution proposals for ${
        activeCRM?.name || 'your CRM'
      }.`,
      time: 'Just now',
    },
  ]);
  const [isThinking, setIsThinking] = useState(false);

  if (!isOpen) return null;

  const quickPrompts = [
    {
      label: 'Optimize Follow-up Workflow',
      query: 'How can I optimize our response delay for newly created leads?',
    },
    {
      label: 'Propose New Evolution',
      query: 'Suggest an evolution proposal to improve lead conversion rate.',
    },
    {
      label: 'Add Dynamic Fields',
      query: 'What high-value fields should I consider adding to my lead entity?',
    },
  ];

  const handleSend = (textToSend?: string) => {
    const query = textToSend || input;
    if (!query.trim()) return;

    const userMsg: Message = {
      sender: 'user',
      text: query,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInput('');
    setIsThinking(true);

    setTimeout(() => {
      setIsThinking(false);
      let reply = '';
      let action: { label: string; route: string } | undefined;

      const q = query.toLowerCase();
      if (q.includes('workflow') || q.includes('follow-up') || q.includes('delay')) {
        reply = `Based on your CRM configuration, you have workflows registered. I recommend navigating to the Evolution Center to draft an automated follow-up proposal with a 12-hour trigger window.`;
        action = { label: 'Go to Evolution Center', route: '/evolution' };
      } else if (q.includes('evolution') || q.includes('conversion') || q.includes('propose')) {
        reply = `I have analyzed your lead conversion rate (${(0.25 * 100).toFixed(0)}%). You can generate an objective-based evolution proposal now to automatically optimize pipeline progression.`;
        action = { label: 'Review Evolution Proposals', route: '/evolution' };
      } else if (q.includes('field') || q.includes('entity') || q.includes('crm')) {
        reply = `In ${activeCRM?.name || 'your CRM'}, dynamic records support text, email, select, date, and numbers. To evolve your schema structure, draft a proposal or generate an updated CRM specification.`;
        action = { label: 'Explore Generator', route: '/create-crm' };
      } else {
        reply = `Understood. AURA's backend provider interface allows seamless evaluation of your prompt. Ready to apply controlled architectural changes with 2-stage human approval.`;
      }

      setMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: reply,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          action,
        },
      ]);
    }, 700);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden pointer-events-none">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity pointer-events-auto"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 max-w-md w-full flex pl-10 pointer-events-auto">
        <div className="w-full bg-white shadow-2xl flex flex-col border-l border-slate-200 animate-fade-in">
          {/* Header */}
          <div className="p-5 border-b border-slate-100 bg-gradient-to-r from-aura-navy via-aura-deep to-aura-navy text-white flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-aura-cyan/20 border border-aura-cyan/30 flex items-center justify-center text-aura-cyan shadow-glow-cyan">
                <Sparkles className="w-5 h-5 text-aura-cyan" />
              </div>
              <div>
                <h3 className="font-bold text-sm tracking-wide flex items-center gap-2">
                  AURA AI Assistant
                  <span className="text-[10px] bg-aura-cyan text-aura-navy px-1.5 py-0.5 rounded font-extrabold uppercase">
                    Beta
                  </span>
                </h3>
                <p className="text-xs text-slate-300">
                  {activeCRM ? `Context: ${activeCRM.name}` : 'CRM Intelligence'}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Quick Prompts */}
          <div className="p-3 bg-slate-50 border-b border-slate-100 flex gap-2 overflow-x-auto">
            {quickPrompts.map((qp, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(qp.query)}
                className="text-[11px] whitespace-nowrap bg-white border border-slate-200 hover:border-aura-cyan px-2.5 py-1.5 rounded-full text-slate-700 hover:text-aura-deep font-medium transition-colors shadow-2xs flex items-center gap-1.5 shrink-0"
              >
                <Lightbulb className="w-3 h-3 text-aura-cyan" />
                {qp.label}
              </button>
            ))}
          </div>

          {/* Message List */}
          <div className="flex-1 p-5 overflow-y-auto space-y-4">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex flex-col ${
                  m.sender === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                    m.sender === 'user'
                      ? 'bg-aura-deep text-white rounded-tr-xs'
                      : 'bg-slate-100 text-aura-charcoal rounded-tl-xs border border-slate-200/60'
                  }`}
                >
                  <p>{m.text}</p>
                  {m.action && (
                    <button
                      onClick={() => {
                        onClose();
                        navigate(m.action!.route);
                      }}
                      className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-semibold text-aura-cyan hover:underline bg-white px-2.5 py-1 rounded-md shadow-2xs text-aura-deep"
                    >
                      <Zap className="w-3.5 h-3.5 text-amber-500" />
                      {m.action.label}
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                </div>
                <span className="text-[10px] text-slate-400 mt-1 px-1">{m.time}</span>
              </div>
            ))}

            {isThinking && (
              <div className="flex items-center gap-2 text-xs text-slate-400 italic">
                <Bot className="w-4 h-4 text-aura-cyan animate-spin" />
                <span>AURA Copilot is evaluating context...</span>
              </div>
            )}
          </div>

          {/* Input Box */}
          <div className="p-4 border-t border-slate-100 bg-white">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask AURA to optimize fields, workflows, or evolutions..."
                className="flex-1 text-xs border border-slate-300 rounded-xl px-3.5 py-2.5 focus:outline-none focus:border-aura-cyan focus:ring-1 focus:ring-aura-cyan"
              />
              <button
                type="submit"
                disabled={!input.trim() || isThinking}
                className="bg-aura-navy hover:bg-aura-deep text-white p-2.5 rounded-xl disabled:opacity-40 transition-colors shadow-subtle shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
            <p className="text-[10px] text-slate-400 mt-2 text-center">
              Self-evolving CRM assistant — drafts require explicit operator approval.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
