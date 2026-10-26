/**
 * ChatContext — persistent state for the CRM Chat builder.
 *
 * Lifts all CRMChatPage state out of the component so that navigating away
 * and returning does not erase the user's conversation progress.
 *
 * Scoping and security:
 * - State is keyed by authenticated user ID. A different user logging in
 *   receives a fresh, empty session.
 * - State is held in React memory (not localStorage/sessionStorage), so it
 *   persists only for the lifetime of the browser tab / session. Refreshing
 *   the page resets the conversation — intentional for a draft builder.
 * - No authentication tokens, secrets, or CRM IDs from other tenants are
 *   stored here.
 * - The draft CRM configuration is already validated by the backend before
 *   it reaches this context.
 * - clearChat() is called on logout and when the user explicitly starts over.
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { CRMConfiguration } from '@/types/crm';
import { useAuth } from './AuthContext';

// ── Shared types (re-exported for CRMChatPage) ─────────────────────

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  response_source?: 'llm' | 'tool_result' | 'rule' | 'fallback' | 'error';
  isLoading?: boolean;
  choices?: string[];
}

export interface QuestAnswers {
  crm_type?: string;
  tracks?: string;
  pipeline_stages?: string;
  key_fields?: string;
  team_size?: string;
}

export type CrmTypeId =
  | 'sales_pipeline'
  | 'client_management'
  | 'customer_support'
  | 'all_in_one'
  | 'custom';

export interface QuestionSpec {
  key: keyof QuestAnswers;
  text: string;
  choices: string[];
}

// ── Welcome message constant ───────────────────────────────────────

export const WELCOME_MESSAGE: ChatMessage = {
  role: 'assistant',
  response_source: 'rule',
  content:
    "Hi! I'm AURA, your AI CRM architect. " +
    'Select a CRM type below or describe your business — ' +
    "I'll ask a few quick questions and then build a custom CRM for you.",
};

// ── Context shape ──────────────────────────────────────────────────

interface ChatContextType {
  // Conversation
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;

  // Input
  input: string;
  setInput: React.Dispatch<React.SetStateAction<string>>;

  // Questionnaire
  selectedCrmType: CrmTypeId | null;
  setSelectedCrmType: React.Dispatch<React.SetStateAction<CrmTypeId | null>>;
  questAnswers: QuestAnswers;
  setQuestAnswers: React.Dispatch<React.SetStateAction<QuestAnswers>>;
  pendingQuestion: QuestionSpec | null;
  setPendingQuestion: React.Dispatch<React.SetStateAction<QuestionSpec | null>>;

  // Generation state
  readyToGenerate: boolean;
  setReadyToGenerate: React.Dispatch<React.SetStateAction<boolean>>;
  draftConfig: CRMConfiguration | null;
  setDraftConfig: React.Dispatch<React.SetStateAction<CRMConfiguration | null>>;
  warnings: string[];
  setWarnings: React.Dispatch<React.SetStateAction<string[]>>;

  // Actions
  clearChat: () => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

// ── Provider ───────────────────────────────────────────────────────

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();

  // Track the user whose chat state is currently held
  const [ownerUserId, setOwnerUserId] = useState<string | null>(user?.id ?? null);

  // All chat state lives here — survives route changes within the session
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState('');
  const [selectedCrmType, setSelectedCrmType] = useState<CrmTypeId | null>(null);
  const [questAnswers, setQuestAnswers] = useState<QuestAnswers>({});
  const [pendingQuestion, setPendingQuestion] = useState<QuestionSpec | null>(null);
  const [readyToGenerate, setReadyToGenerate] = useState(false);
  const [draftConfig, setDraftConfig] = useState<CRMConfiguration | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const clearChat = useCallback(() => {
    setMessages([WELCOME_MESSAGE]);
    setInput('');
    setSelectedCrmType(null);
    setQuestAnswers({});
    setPendingQuestion(null);
    setReadyToGenerate(false);
    setDraftConfig(null);
    setWarnings([]);
  }, []);

  // ── User scoping: clear state when the authenticated user changes ──
  // This prevents one user's draft from being visible after logout/login.
  useEffect(() => {
    const currentId = user?.id ?? null;
    if (currentId !== ownerUserId) {
      // Different user (or logout) — wipe everything
      clearChat();
      setOwnerUserId(currentId);
    }
  }, [user?.id, ownerUserId, clearChat]);

  return (
    <ChatContext.Provider
      value={{
        messages,
        setMessages,
        input,
        setInput,
        selectedCrmType,
        setSelectedCrmType,
        questAnswers,
        setQuestAnswers,
        pendingQuestion,
        setPendingQuestion,
        readyToGenerate,
        setReadyToGenerate,
        draftConfig,
        setDraftConfig,
        warnings,
        setWarnings,
        clearChat,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

// ── Hook ───────────────────────────────────────────────────────────

export const useChat = (): ChatContextType => {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within a ChatProvider');
  return ctx;
};
