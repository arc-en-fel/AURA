import React, { useRef, useEffect, useCallback } from 'react';
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
  ChevronRight,
} from 'lucide-react';
import { useState } from 'react';
import { api } from '@/services/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/context/ToastContext';
import { useCRM } from '@/context/CRMContext';
import {
  useChat,
  CrmTypeId,
  QuestionSpec,
  QuestAnswers,
} from '@/context/ChatContext';

// ── CRM type chip definitions ──────────────────────────────────────

const CRM_TYPES = [
  { id: 'sales_pipeline' as CrmTypeId, label: 'Sales Pipeline', description: 'Leads → Deals' },
  { id: 'client_management' as CrmTypeId, label: 'Client Management', description: 'Accounts & relationships' },
  { id: 'customer_support' as CrmTypeId, label: 'Customer Support', description: 'Tickets & service' },
  { id: 'all_in_one' as CrmTypeId, label: 'All-in-One', description: 'Full CRM suite' },
  { id: 'custom' as CrmTypeId, label: 'Other / Custom', description: 'Describe your own' },
];

// ── Deterministic questionnaire logic ─────────────────────────────

function getNextQuestion(
  answers: QuestAnswers,
  crmType: CrmTypeId | null,
): QuestionSpec | null {
  if (!crmType && !answers.crm_type) {
    return {
      key: 'crm_type',
      text: 'What kind of CRM are you building?',
      choices: [
        'Sales pipeline (leads → deals)',
        'Client / account management',
        'Customer support (tickets)',
        'All-in-one suite',
        "Something else — I'll describe it",
      ],
    };
  }

  const effective = crmType ?? answers.crm_type ?? 'custom';

  if (!answers.tracks) {
    if (effective === 'sales_pipeline') {
      return {
        key: 'tracks',
        text: 'What do you need to track in the pipeline?',
        choices: ['Leads → Deals', 'Contacts + Companies + Deals', 'Leads + Quotes + Invoices', 'Just leads for now'],
      };
    }
    if (effective === 'client_management') {
      return {
        key: 'tracks',
        text: 'What do you need to manage for each client?',
        choices: ['Contacts + account details', 'Projects + deliverables', 'Contracts + renewals', 'All of the above'],
      };
    }
    if (effective === 'customer_support') {
      return {
        key: 'tracks',
        text: 'What does a support ticket need to capture?',
        choices: ['Issue + status + priority', 'Customer info + issue + resolution', 'Bug reports + severity + assignee', 'Custom fields'],
      };
    }
    return {
      key: 'tracks',
      text: 'What are the main things you need to track?',
      choices: ['Leads and deals', 'Customers and accounts', 'Tasks and projects', "Something specific — I'll type it"],
    };
  }

  if (!answers.pipeline_stages) {
    if (effective === 'sales_pipeline') {
      return {
        key: 'pipeline_stages',
        text: 'Which pipeline stages fit your sales process?',
        choices: [
          'New → Contacted → Qualified → Proposal → Won / Lost',
          'Lead → Demo → Trial → Closed Won / Closed Lost',
          'Prospect → Discovery → Negotiation → Signed',
          "I'll describe my own stages",
        ],
      };
    }
    if (effective === 'customer_support') {
      return {
        key: 'pipeline_stages',
        text: 'How does a support ticket move through your team?',
        choices: [
          'Open → In Progress → Resolved → Closed',
          'New → Assigned → Pending → Resolved',
          'Reported → Triaged → In Dev → QA → Done',
          "I'll describe my own stages",
        ],
      };
    }
    if (effective === 'client_management') {
      return {
        key: 'pipeline_stages',
        text: 'How do you track the status of a client relationship?',
        choices: [
          'Prospect → Onboarding → Active → Renewal → Churned',
          'Lead → Trial → Paying → VIP → Inactive',
          'New → Engaged → Partner → Alumni',
          "I'll describe my own stages",
        ],
      };
    }
    return {
      key: 'pipeline_stages',
      text: 'What stages or statuses will your records move through?',
      choices: [
        'New → In Progress → Done',
        'Active → On Hold → Completed → Archived',
        "Custom — I'll type my own stages",
      ],
    };
  }

  if (!answers.key_fields) {
    return {
      key: 'key_fields',
      text: 'What are the most important fields on each record?',
      choices: [
        'Name, email, phone, status',
        'Company, contact name, deal value, close date',
        'Name, priority, assigned to, due date',
        "I'll list my own fields",
      ],
    };
  }

  if (!answers.team_size) {
    return {
      key: 'team_size',
      text: 'How big is the team that will use this CRM?',
      choices: ['Just me', 'Small team (2–10)', 'Medium (10–50)', 'Large (50+)'],
    };
  }

  return null;
}

// Choices that signal the user wants to type a custom answer instead.
// When these are selected, we clear the pending question, focus the input,
// and wait — we do NOT record the choice text as the answer.
const CUSTOM_ANSWER_TRIGGERS = [
  "i'll describe my own",
  "i'll type my own",
  "i'll list my own",
  "something specific",
  "something else",
  "custom —",
  "type your own",
  "describe your own",
];

function isCustomAnswerChoice(choice: string): boolean {
  const lower = choice.toLowerCase();
  return CUSTOM_ANSWER_TRIGGERS.some((t) => lower.includes(t));
}

export const CRMChatPage: React.FC = () => {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  const { refreshCRMs, selectCRM } = useCRM();

  // All persistent state comes from context — survives navigation
  const {
    messages, setMessages,
    input, setInput,
    selectedCrmType, setSelectedCrmType,
    questAnswers, setQuestAnswers,
    pendingQuestion, setPendingQuestion,
    readyToGenerate, setReadyToGenerate,
    draftConfig, setDraftConfig,
    warnings, setWarnings,
    clearChat,
  } = useChat();

  // Transient UI-only flags — these don't need to survive navigation
  const [isSending, setIsSending] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!isSending && !isGenerating && !draftConfig) {
      inputRef.current?.focus();
    }
  }, [isSending, isGenerating, draftConfig]);

  // ── Deterministic completeness check ──────────────────────────────

  const checkAndAdvance = useCallback(
    (updatedAnswers: QuestAnswers, currentCrmType: CrmTypeId | null) => {
      const next = getNextQuestion(updatedAnswers, currentCrmType);
      if (next) {
        setPendingQuestion(next);
        setReadyToGenerate(false);
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: next.text, choices: next.choices },
        ]);
      } else {
        setPendingQuestion(null);
        setReadyToGenerate(true);
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content:
              "I have everything I need to design your CRM! " +
              "Click **Generate My CRM** when you're ready.",
          },
        ]);
      }
    },
    [setMessages, setPendingQuestion, setReadyToGenerate],
  );

  // ── CRM type chip selection ────────────────────────────────────────

  const handleSelectCrmType = (typeId: CrmTypeId) => {
    if (draftConfig || isSending || isGenerating) return;

    setSelectedCrmType(typeId);
    const label = CRM_TYPES.find((t) => t.id === typeId)?.label ?? typeId;
    const userMsg = { role: 'user' as const, content: `I want to build a ${label} CRM.` };
    setMessages((prev) => [...prev, userMsg]);

    const updated: QuestAnswers = { ...questAnswers, crm_type: typeId };
    setQuestAnswers(updated);
    checkAndAdvance(updated, typeId);
  };

  // ── Numbered choice selection ──────────────────────────────────────

  const handleSelectChoice = (choice: string) => {
    if (!pendingQuestion || isSending || isGenerating || draftConfig) return;

    // If the user picked a "type my own" option, show a prompt in the chat
    // and wait — focus the input so they can type their custom answer.
    if (isCustomAnswerChoice(choice)) {
      const userMsg = { role: 'user' as const, content: choice };
      setMessages((prev) => [
        ...prev,
        userMsg,
        {
          role: 'assistant',
          content: `Sure! Type your own answer in the box below and press Enter.`,
        },
      ]);
      // Keep pendingQuestion so the typed answer goes to the right field
      setTimeout(() => inputRef.current?.focus(), 50);
      return;
    }

    submitAnswer(choice, pendingQuestion.key);
  };

  // ── Core: submit a text or choice answer ──────────────────────────

  const submitAnswer = useCallback(
    async (text: string, answerKey?: keyof QuestAnswers) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      setInput('');
      setError(null);

      const userMsg = { role: 'user' as const, content: trimmed };

      // Build the updated message array synchronously for the AI payload
      // We cannot rely on `messages` from the closure being current after
      // state batching, so we derive the payload from the functional updater.
      let snapshotForPayload: typeof messages = [];
      setMessages((prev) => {
        snapshotForPayload = [...prev, userMsg];
        return snapshotForPayload;
      });

      const key = answerKey ?? pendingQuestion?.key;
      const updatedAnswers: QuestAnswers = key
        ? { ...questAnswers, [key]: trimmed }
        : questAnswers;

      if (key) {
        setQuestAnswers(updatedAnswers);
        setPendingQuestion(null);
        // Give React a tick to flush state before checking completeness
        setTimeout(() => checkAndAdvance(updatedAnswers, selectedCrmType), 0);
        return;
      }

      // Free-form message — send to AI
      setIsSending(true);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '', isLoading: true },
      ]);

      try {
        // Use the snapshot we captured above; filter out loading placeholders
        const payload = snapshotForPayload
          .filter((m) => !m.isLoading)
          .map((m) => ({ role: m.role, content: m.content }));

        const res = await api.chatCRM(payload, false, selectedCrmType ?? undefined);

        const reply = res.reply ?? "Thanks! Let me ask you one more thing.";
        const ready = res.ready_to_generate ?? false;

        setMessages((prev) => {
          const without = prev.filter((m) => !m.isLoading);
          return [...without, { role: 'assistant', content: reply }];
        });

        // Always update readyToGenerate from the AI response
        if (ready) {
          setReadyToGenerate(true);
          setPendingQuestion(null);
        } else {
          setReadyToGenerate(false);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to send message.';
        setError(msg);
        setMessages((prev) => prev.filter((m) => !m.isLoading));
      } finally {
        setIsSending(false);
      }
    },
    [
      pendingQuestion, questAnswers, selectedCrmType,
      checkAndAdvance, setMessages, setInput, setQuestAnswers,
      setPendingQuestion, setReadyToGenerate,
    ],
  );

  // ── Send from text input ───────────────────────────────────────────

  const sendMessage = () => {
    if (!input.trim() || isSending || isGenerating) return;
    submitAnswer(input.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Generate CRM ───────────────────────────────────────────────────

  const handleGenerateCRM = async () => {
    setIsGenerating(true);
    setError(null);

    try {
      const payload = messages
        .filter((m) => !m.isLoading)
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await api.chatCRM(payload, true, selectedCrmType ?? undefined);

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
            `${config.entities.length} entity type(s), ` +
            `${config.entities.reduce((s, e) => s + e.fields.length, 0)} fields, ` +
            `${config.pipeline_stages.length} pipeline stages. ` +
            `Review it below and click Save to activate.`,
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

  // ── Save CRM ───────────────────────────────────────────────────────

  const handleSaveCRM = async () => {
    if (!draftConfig) return;
    setIsSaving(true);
    try {
      const saved = await api.saveCRM(draftConfig);
      await refreshCRMs();
      await selectCRM(saved.crm_id);
      success(`CRM "${saved.name}" saved and activated!`);
      // Clear the chat so next visit starts fresh
      clearChat();
      navigate(`/crms/${saved.crm_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save CRM.';
      toastError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  // ── Reset ──────────────────────────────────────────────────────────

  const handleReset = () => {
    clearChat();
    setError(null);
  };

  // ── Render ─────────────────────────────────────────────────────────

  const showChips = messages.length <= 2 && !selectedCrmType && !draftConfig;

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto space-y-4">

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-aura-cyan text-[11px] font-bold uppercase tracking-wider mb-2">
            <MessageCircle className="w-3.5 h-3.5" />
            AI CRM Architect
          </div>
          <h2 className="text-xl font-extrabold text-aura-navy">Build Your CRM</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Answer a few questions and AURA will design a custom CRM for your business.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleReset}
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
        >
          Start Over
        </Button>
      </div>

      {/* ── CRM Type Chips ─────────────────────────────────────────── */}
      {showChips && (
        <div className="space-y-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Choose a CRM type to get started:
          </p>
          <div className="flex flex-wrap gap-2">
            {CRM_TYPES.map((t) => (
              <button
                key={t.id}
                onClick={() => handleSelectCrmType(t.id)}
                className="flex flex-col items-start px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:border-aura-cyan hover:bg-cyan-50/40 transition-all text-left focus:outline-none focus:ring-2 focus:ring-aura-cyan/40 group"
                aria-label={`Select ${t.label}`}
              >
                <span className="text-xs font-bold text-aura-navy group-hover:text-aura-deep">
                  {t.label}
                </span>
                <span className="text-[10px] text-slate-400">{t.description}</span>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-slate-400">
            Or just type what you need below — AURA will figure out the rest.
          </p>
        </div>
      )}

      {/* ── Selected CRM type badge ────────────────────────────────── */}
      {selectedCrmType && !draftConfig && (
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-slate-500">CRM type:</span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-aura-cyan/10 border border-aura-cyan/30 text-aura-cyan text-[11px] font-bold">
            {CRM_TYPES.find((t) => t.id === selectedCrmType)?.label}
            <button
              onClick={() => {
                setSelectedCrmType(null);
                setQuestAnswers((a) => { const n = { ...a }; delete n.crm_type; return n; });
              }}
              className="text-aura-cyan/60 hover:text-aura-cyan ml-0.5"
              title="Change CRM type"
            >
              ×
            </button>
          </span>
        </div>
      )}

      {/* ── Chat Window ────────────────────────────────────────────── */}
      <Card
        className="flex flex-col flex-1 overflow-hidden p-0 border-slate-200"
        style={{ minHeight: '400px', maxHeight: '520px' }}
      >
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === 'assistant'
                    ? 'bg-gradient-to-tr from-aura-deep to-aura-cyan text-white'
                    : 'bg-slate-200 text-slate-600'
                }`}
              >
                {msg.role === 'assistant' ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
              </div>

              <div className="flex flex-col gap-2 max-w-[80%]">
                <div
                  className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
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

                {/* Numbered answer choices */}
                {msg.role === 'assistant' && msg.choices && msg.choices.length > 0 && !draftConfig && (
                  <div className="space-y-1.5 ml-1">
                    {msg.choices.map((choice, ci) => (
                      <button
                        key={ci}
                        onClick={() => handleSelectChoice(choice)}
                        disabled={isSending || isGenerating}
                        className="flex items-center gap-2.5 w-full text-left px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-aura-cyan hover:bg-cyan-50/30 transition-all text-xs text-slate-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-aura-cyan/30 group"
                      >
                        <span className="w-5 h-5 rounded-full border border-slate-300 bg-slate-50 text-[10px] font-bold text-slate-500 flex items-center justify-center shrink-0 group-hover:border-aura-cyan group-hover:text-aura-cyan">
                          {ci + 1}
                        </span>
                        <span>{choice}</span>
                        <ChevronRight className="w-3.5 h-3.5 text-slate-300 ml-auto group-hover:text-aura-cyan" />
                      </button>
                    ))}
                  </div>
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
              placeholder={
                pendingQuestion
                  ? 'Select an option above or type your own answer…'
                  : 'Type your message… (Enter to send)'
              }
              disabled={isSending || isGenerating}
              className="flex-1 resize-none text-sm px-3 py-2 rounded-xl border border-slate-300 focus:border-aura-cyan outline-none transition-colors disabled:opacity-50 max-h-32"
              style={{ minHeight: '40px' }}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || isSending || isGenerating}
              className="p-2.5 rounded-xl bg-aura-navy text-white hover:bg-aura-deep disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
            >
              {isSending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        )}
      </Card>

      {/* ── Error ──────────────────────────────────────────────────── */}
      {error && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-500" />
          <div>
            <p className="font-semibold">Error</p>
            <p>{error}</p>
          </div>
        </div>
      )}

      {/* ── Fallback warning ───────────────────────────────────────── */}
      {warnings.length > 0 && (
        <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-1">
          <p className="font-bold">Note:</p>
          {warnings.map((w, i) => <p key={i}>• {w}</p>)}
        </div>
      )}

      {/* ── Generate button ─────────────────────────────────────────── */}
      {!draftConfig && readyToGenerate && (
        <Card className="p-4 border-aura-cyan/30 bg-cyan-50/50">
          <div className="flex items-center justify-between gap-4 flex-wrap">
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

      {/* ── Draft CRM Preview ──────────────────────────────────────── */}
      {draftConfig && (
        <Card className="p-5 border-slate-200 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-amber-600 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full">
                Draft Proposal
              </span>
              <h3 className="text-lg font-bold text-aura-navy mt-1">{draftConfig.name}</h3>
              <p className="text-xs text-slate-500">
                Industry: <span className="font-semibold">{draftConfig.industry}</span>
                {' · '}Schema: <span className="font-semibold">{draftConfig.schema_version}</span>
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleReset}
                leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
              >
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

          {draftConfig.pipeline_stages.length > 0 && (
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
          )}

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
