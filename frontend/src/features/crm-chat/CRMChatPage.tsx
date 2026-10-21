import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageCircle,
  Send,
  Sparkles,
  Bot,
  User,
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Save,
} from 'lucide-react';
import { api } from '@/services/api';
import { CRMConfiguration } from '@/types/crm';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/context/ToastContext';
import { useCRM } from '@/context/CRMContext';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  isLoading?: boolean;
}

const WELCOME_MESSAGE: Message = {
  role: 'assistant',
  content:
    "Hi! I'm AURA, your AI CRM architect. I'll ask you a few quick questions about your business so I can design a custom CRM that fits exactly what you need.\n\nLet's start — what kind of business is this CRM for?",
};

export const CRMChatPage: React.FC = () => {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  const { refreshCRMs, selectCRM } = useCRM();

  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [readyToGenerate, setReadyToGenerate] = useState(false);
  const [draftConfig, setDraftConfig] = useState<CRMConfiguration | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-focus input
  useEffect(() => {
    if (!isSending && !isGenerating && !draftConfig) {
      inputRef.current?.focus();
    }
  }, [isSending, isGenerating, draftConfig]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || isSending || isGenerating) return;

    setInput('');
    setError(null);

    // Add user message immediately
    const userMsg: Message = { role: 'user', content: text };
    const loadingMsg: Message = { role: 'assistant', content: '', isLoading: true };
    const updatedMessages = [...messages, userMsg];
    setMessages([...updatedMessages, loadingMsg]);
    setIsSending(true);

    try {
      // Only send actual messages (not loading placeholder)
      const payload = updatedMessages.map((m) => ({ role: m.role, content: m.content }));
      const res = await api.chatCRM(payload, false);

      const reply = res.reply ?? "Thanks! I'm gathering more details.";
      const ready = res.ready_to_generate ?? false;

      setMessages([
        ...updatedMessages,
        { role: 'assistant', content: reply },
      ]);
      setReadyToGenerate(ready);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to send message.';
      setError(msg);
      // Remove loading message on error
      setMessages(updatedMessages);
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleGenerateCRM = async () => {
    setIsGenerating(true);
    setError(null);

    try {
      const payload = messages
        .filter((m) => !m.isLoading)
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await api.chatCRM(payload, true);

      if (!res.configuration) throw new Error('No configuration returned.');

      const config = res.configuration;
      setDraftConfig(config);
      setWarnings(res.warnings ?? []);

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            `✅ Your **${config.name}** CRM is ready! ` +
            `I've created ${config.entities.length} entity type(s) with ${
              config.entities.reduce((sum, e) => sum + e.fields.length, 0)
            } fields and ${config.pipeline_stages.length} pipeline stages. ` +
            `Review it below and click Save to activate it.`,
        },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'CRM generation failed.';
      setError(msg);
      toastError(msg);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveCRM = async () => {
    if (!draftConfig) return;
    setIsSaving(true);
    try {
      const saved = await api.saveCRM(draftConfig);
      await refreshCRMs();
      await selectCRM(saved.crm_id);
      success(`CRM "${saved.name}" saved and activated!`);
      navigate(`/crms/${saved.crm_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save CRM.';
      toastError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    setMessages([WELCOME_MESSAGE]);
    setInput('');
    setReadyToGenerate(false);
    setDraftConfig(null);
    setWarnings([]);
    setError(null);
  };

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-aura-cyan text-[11px] font-bold uppercase tracking-wider mb-2">
            <MessageCircle className="w-3.5 h-3.5" />
            AI CRM Architect
          </div>
          <h2 className="text-xl font-extrabold text-aura-navy">Build Your CRM</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Chat with AURA to design a custom CRM tailored to your business.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleReset} leftIcon={<RefreshCw className="w-3.5 h-3.5" />}>
          Start Over
        </Button>
      </div>

      {/* Chat window */}
      <Card className="flex flex-col flex-1 overflow-hidden p-0 border-slate-200" style={{ minHeight: '420px', maxHeight: '520px' }}>
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
            >
              {/* Avatar */}
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === 'assistant'
                    ? 'bg-gradient-to-tr from-aura-deep to-aura-cyan text-white'
                    : 'bg-slate-200 text-slate-600'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <Bot className="w-4 h-4" />
                ) : (
                  <User className="w-4 h-4" />
                )}
              </div>

              {/* Bubble */}
              <div
                className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'assistant'
                    ? 'bg-slate-50 border border-slate-200 text-slate-800 rounded-tl-sm'
                    : 'bg-aura-navy text-white rounded-tr-sm'
                }`}
              >
                {msg.isLoading ? (
                  <span className="flex items-center gap-2 text-slate-400">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span className="text-xs">AURA is thinking…</span>
                  </span>
                ) : (
                  <span className="whitespace-pre-wrap">{msg.content}</span>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        {!draftConfig && (
          <div className="border-t border-slate-100 p-3 flex gap-2 items-end">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your answer… (Enter to send)"
              disabled={isSending || isGenerating}
              className="flex-1 resize-none text-sm px-3 py-2 rounded-xl border border-slate-300 focus:border-aura-cyan outline-none transition-colors disabled:opacity-50 max-h-32"
              style={{ minHeight: '40px' }}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || isSending || isGenerating}
              className="p-2.5 rounded-xl bg-aura-navy text-white hover:bg-aura-deep disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
            >
              {isSending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        )}
      </Card>

      {/* Error */}
      {error && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-500" />
          <div>
            <p className="font-semibold">Error</p>
            <p>{error}</p>
          </div>
        </div>
      )}

      {/* Fallback warning */}
      {warnings.length > 0 && (
        <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-1">
          <p className="font-bold">Architectural Warnings:</p>
          {warnings.map((w, i) => <p key={i}>• {w}</p>)}
        </div>
      )}

      {/* Generate CRM button — shown when ready */}
      {!draftConfig && readyToGenerate && (
        <Card className="p-4 border-aura-cyan/30 bg-cyan-50/50">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-5 h-5 text-aura-cyan shrink-0" />
              <div>
                <p className="text-sm font-bold text-aura-navy">Ready to generate!</p>
                <p className="text-xs text-slate-500">AURA has enough information to build your CRM.</p>
              </div>
            </div>
            <Button
              variant="primary"
              onClick={handleGenerateCRM}
              isLoading={isGenerating}
              leftIcon={<Sparkles className="w-4 h-4 text-aura-cyan" />}
            >
              Generate My CRM
            </Button>
          </div>
        </Card>
      )}

      {/* Draft CRM Preview */}
      {draftConfig && (
        <Card className="p-5 border-slate-200 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-amber-600 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full">
                Draft Proposal
              </span>
              <h3 className="text-lg font-bold text-aura-navy mt-1">{draftConfig.name}</h3>
              <p className="text-xs text-slate-500">
                Industry: <span className="font-semibold">{draftConfig.industry}</span> ·{' '}
                Schema: <span className="font-semibold">{draftConfig.schema_version}</span>
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handleReset} leftIcon={<RefreshCw className="w-3.5 h-3.5" />}>
                Restart
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSaveCRM}
                isLoading={isSaving}
                leftIcon={<Save className="w-4 h-4" />}
              >
                Save & Activate CRM
              </Button>
            </div>
          </div>

          {/* Pipeline stages */}
          <div>
            <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider mb-2">
              Pipeline Stages
            </p>
            <div className="flex flex-wrap gap-2">
              {draftConfig.pipeline_stages.map((s, i) => (
                <span key={i} className="px-2.5 py-1 rounded-full bg-slate-100 border border-slate-200 text-xs text-slate-700 font-medium">
                  {s}
                </span>
              ))}
            </div>
          </div>

          {/* Entities */}
          {draftConfig.entities.map((entity, ei) => (
            <div key={ei} className="border border-slate-200 rounded-xl p-3.5 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-aura-navy">{entity.label}</span>
                <span className="text-[10px] font-mono text-slate-400">({entity.name})</span>
                <span className="ml-auto text-[10px] text-slate-400">{entity.fields.length} fields</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                {entity.fields.map((field, fi) => (
                  <div key={fi} className="px-2 py-1.5 rounded-lg bg-slate-50 border border-slate-100 text-xs">
                    <span className="font-semibold text-slate-700">{field.label}</span>
                    <span className="ml-1 text-slate-400">· {field.type}</span>
                    {field.required && <span className="ml-1 text-rose-400 font-bold">*</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
};
