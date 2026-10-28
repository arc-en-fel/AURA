import React, { useState, useRef, useEffect } from 'react';
import {
  Sparkles,
  Send,
  X,
  ArrowRight,
  Zap,
  Lightbulb,
  Loader2,
} from 'lucide-react';
import { useCRM } from '@/context/CRMContext';
import { useNavigate } from 'react-router-dom';
import { api } from '@/services/api';

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

interface ToolCall {
  name: string;
  arguments: Record<string, any>;
}

function makeWelcome(crmName: string): Message {
  return {
    sender: 'ai',
    text:
      `Hello! I'm your AURA AI Copilot. I can answer questions about ` +
      `${crmName}, explain workflows, guide you to any AURA feature, ` +
      `or suggest improvements. What would you like to know?`,
    time: 'Just now',
  };
}

/**
 * Parse TOOL_CALL: {...} JSON objects from LLM reply.
 * Returns list of {name, arguments} objects.
 */
function parseToolCalls(text: string): ToolCall[] {
  const toolCalls: ToolCall[] = [];
  
  // Match TOOL_CALL: {...} pattern (regex handles nested JSON up to ~2 levels)
  const regex = /TOOL_CALL:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})/g;
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    try {
      const call_json = match[1];
      const call_obj = JSON.parse(call_json) as ToolCall;
      if (call_obj.name && call_obj.arguments) {
        toolCalls.push(call_obj);
      }
    } catch (e) {
      console.warn('Failed to parse tool call:', match[1], e);
    }
  }
  
  return toolCalls;
}

/**
 * Remove TOOL_CALL markers from text for display.
 */
function cleanToolCallMarkers(text: string): string {
  return text.replace(/TOOL_CALL:\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, '').trim();
}

export const AIAssistantDrawer: React.FC<AIAssistantDrawerProps> = ({ isOpen, onClose }) => {
  const { activeCRM } = useCRM();
  const navigate = useNavigate();

  const crmName = activeCRM?.name ?? 'your CRM';
  const crmId = activeCRM?.crm_id ?? null;

  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);

  // Conversation history — persists while the drawer component stays mounted.
  // Resets when the drawer is first opened after being closed.
  const [messages, setMessages] = useState<Message[]>([makeWelcome(crmName)]);

  // Confirmation dialog state for dangerous tool operations
  interface ConfirmationState {
    visible: boolean;
    title: string;
    message: string;
    toolCall?: ToolCall;
    onConfirm?: () => void;
    onCancel?: () => void;
  }
  const [confirmation, setConfirmation] = useState<ConfirmationState>({
    visible: false,
    title: '',
    message: '',
  });

  // Reset greeting when a different CRM becomes active
  const lastCrmId = useRef<string | null>(crmId);
  useEffect(() => {
    if (crmId !== lastCrmId.current) {
      lastCrmId.current = crmId;
      setMessages([makeWelcome(activeCRM?.name ?? 'your CRM')]);
    }
  }, [crmId, activeCRM?.name]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  if (!isOpen) return null;

  /**
   * Execute a tool call via the backend.
   */
  const executeToolCall = async (toolCall: ToolCall): Promise<{ success: boolean; error?: string }> => {
    if (!crmId) {
      return { success: false, error: 'No active CRM' };
    }

    try {
      await api.executeToolCall(crmId, {
        tool_name: toolCall.name,
        arguments: toolCall.arguments,
      });

      // Show success message in chat
      const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const successMsg: Message = {
        sender: 'ai',
        text: `✓ Successfully executed '${toolCall.name}'. Changes saved.`,
        time: now,
      };
      setMessages((prev) => [...prev, successMsg]);

      return { success: true };
    } catch (err: unknown) {
      const errorText = err instanceof Error ? err.message : 'Tool execution failed';
      const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const errorMsg: Message = {
        sender: 'ai',
        text: `✗ Operation failed: ${errorText}`,
        time: now,
      };
      setMessages((prev) => [...prev, errorMsg]);

      return { success: false, error: errorText };
    }
  };

  /**
   * Show confirmation dialog for dangerous operations (delete, remove_field, remove_stage).
   * Returns a promise that resolves when user confirms or cancels.
   */
  const showToolConfirmationDialog = (toolCall: ToolCall): Promise<void> => {
    return new Promise((resolve) => {
      const handleConfirm = async () => {
        setConfirmation({ visible: false, title: '', message: '' });
        await executeToolCall(toolCall);
        resolve();
      };

      const handleCancel = () => {
        setConfirmation({ visible: false, title: '', message: '' });
        const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        setMessages((prev) => [
          ...prev,
          {
            sender: 'ai',
            text: `⚠ Operation cancelled. No changes made.`,
            time: now,
          },
        ]);
        resolve();
      };

      setConfirmation({
        visible: true,
        title: `Confirm ${toolCall.name}`,
        message: `This action cannot be undone. Are you sure you want to proceed?`,
        toolCall,
        onConfirm: handleConfirm,
        onCancel: handleCancel,
      });
    });
  };

  /**
   * Refresh data after tool execution (dispatch custom events for other components to listen to).
   */
  const refreshDataAfterToolExecution = (toolCalls: ToolCall[]) => {
    const needsRecordsRefresh = toolCalls.some(
      (t) => ['create_record', 'update_record', 'delete_record'].includes(t.name)
    );

    const needsConfigRefresh = toolCalls.some(
      (t) => ['add_crm_field', 'update_crm_field', 'delete_crm_field', 'add_crm_stage', 'delete_crm_stage'].includes(t.name)
    );

    if (needsRecordsRefresh) {
      window.dispatchEvent(new CustomEvent('records-changed'));
    }

    if (needsConfigRefresh) {
      window.dispatchEvent(new CustomEvent('crm-config-changed'));
    }
  };

  const quickPrompts = [
    { label: 'CRM Fields', query: `What fields does my ${crmName} have?` },
    { label: 'Improve Conversion', query: 'How can I improve my lead conversion rate?' },
    { label: 'Workflow Help', query: 'How do workflows work in AURA?' },
    { label: 'Evolution Center', query: 'How do I propose a CRM improvement?' },
  ];

  const handleSend = async (textToSend?: string) => {
    const query = (textToSend || input).trim();
    if (!query || isThinking) return;

    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg: Message = { sender: 'user', text: query, time: now };

    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    if (!textToSend) setInput('');
    setIsThinking(true);

    try {
      // Build payload: only send role/content pairs (no timestamps or actions)
      const payload = updatedMessages.map((m) => ({
        role: m.sender === 'ai' ? 'assistant' : 'user',
        content: m.text,
      })) as { role: 'user' | 'assistant'; content: string }[];

      const res = await api.copilotChat(payload, crmId);

      // Parse tool calls from the reply
      const toolCalls = parseToolCalls(res.reply);
      
      // Remove tool call markers from display text
      const displayText = cleanToolCallMarkers(res.reply);

      const replyTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      // If there are tool calls, execute them
      if (toolCalls.length > 0) {
        for (const toolCall of toolCalls) {
          // Check if tool requires confirmation (dangerous operations)
          const dangerousTools = ['delete_record', 'delete_crm_field', 'delete_crm_stage'];
          if (dangerousTools.includes(toolCall.name)) {
            // Show confirmation UI
            await showToolConfirmationDialog(toolCall);
          } else {
            // Execute immediately
            await executeToolCall(toolCall);
          }
        }
      }

      // Add AI response to chat
      const aiMsg: Message = {
        sender: 'ai',
        text: displayText,
        time: replyTime,
        action:
          res.nav_route && res.nav_label
            ? { label: res.nav_label, route: res.nav_route }
            : undefined,
      };
      setMessages((prev) => [...prev, aiMsg]);

      // Refresh relevant data after tool execution
      if (toolCalls.length > 0) {
        refreshDataAfterToolExecution(toolCalls);
      }

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Something went wrong.';
      const errTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      setMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: `I ran into an issue: ${msg}. Please try again.`,
          time: errTime,
        },
      ]);
    } finally {
      setIsThinking(false);
    }
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
              <div className="w-9 h-9 rounded-xl bg-aura-cyan/20 border border-aura-cyan/30 flex items-center justify-center shadow-glow-cyan">
                <Sparkles className="w-5 h-5 text-aura-cyan" />
              </div>
              <div>
                <h3 className="font-bold text-sm tracking-wide flex items-center gap-2">
                  AURA AI Copilot
                  <span className="text-[10px] bg-aura-cyan text-aura-navy px-1.5 py-0.5 rounded font-extrabold uppercase">
                    Live
                  </span>
                </h3>
                <p className="text-xs text-slate-300">
                  {activeCRM ? `Context: ${activeCRM.name}` : 'No active CRM'}
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
                disabled={isThinking}
                className="text-[11px] whitespace-nowrap bg-white border border-slate-200 hover:border-aura-cyan px-2.5 py-1.5 rounded-full text-slate-700 hover:text-aura-deep font-medium transition-colors shadow-2xs flex items-center gap-1.5 shrink-0 disabled:opacity-40"
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
                className={`flex flex-col ${m.sender === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                    m.sender === 'user'
                      ? 'bg-aura-deep text-white rounded-tr-xs'
                      : 'bg-slate-100 text-aura-charcoal rounded-tl-xs border border-slate-200/60'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{m.text}</p>
                  {m.action && (
                    <button
                      onClick={() => {
                        onClose();
                        navigate(m.action!.route);
                      }}
                      className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-semibold bg-white px-2.5 py-1 rounded-md shadow-2xs text-aura-deep hover:text-aura-cyan transition-colors"
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
                <Loader2 className="w-4 h-4 text-aura-cyan animate-spin" />
                <span>AURA is thinking…</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Box */}
          <div className="p-4 border-t border-slate-100 bg-white">
            <form
              onSubmit={(e) => { e.preventDefault(); handleSend(); }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your CRM, records, workflows…"
                disabled={isThinking}
                className="flex-1 text-xs border border-slate-300 rounded-xl px-3.5 py-2.5 focus:outline-none focus:border-aura-cyan focus:ring-1 focus:ring-aura-cyan disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || isThinking}
                className="bg-aura-navy hover:bg-aura-deep text-white p-2.5 rounded-xl disabled:opacity-40 transition-colors shadow-subtle shrink-0"
              >
                {isThinking
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Send className="w-4 h-4" />
                }
              </button>
            </form>
            <p className="text-[10px] text-slate-400 mt-2 text-center">
              AI responses are informational — all CRM changes require explicit approval.
            </p>
          </div>
        </div>
      </div>

      {/* Confirmation Modal for Dangerous Operations */}
      {confirmation.visible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm pointer-events-auto">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 p-6 border border-slate-200 animate-fade-in">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Zap className="w-6 h-6 text-amber-600" />
              </div>
              <h2 className="text-lg font-bold text-aura-navy">{confirmation.title}</h2>
            </div>

            <p className="text-sm text-slate-600 mb-6">{confirmation.message}</p>

            <div className="flex gap-3 justify-end">
              <button
                onClick={confirmation.onCancel}
                className="px-4 py-2 rounded-lg bg-slate-100 text-slate-700 font-medium text-sm hover:bg-slate-200 transition-colors flex items-center gap-2"
              >
                <X className="w-4 h-4" />
                Cancel
              </button>
              <button
                onClick={confirmation.onConfirm}
                className="px-4 py-2 rounded-lg bg-aura-cyan text-aura-navy font-bold text-sm hover:bg-cyan-400 transition-colors flex items-center gap-2"
              >
                <Send className="w-4 h-4" />
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
