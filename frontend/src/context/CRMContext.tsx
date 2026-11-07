import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { CRMSummary, CRMEntity } from '@/types/crm';
import { api } from '@/services/api';
import { useAuth } from './AuthContext';

interface CRMContextType {
  crms: CRMSummary[];
  activeCRM: CRMSummary | null;
  activeEntity: CRMEntity | null;
  isLoading: boolean;
  error: string | null;
  refreshCRMs: () => Promise<void>;
  selectCRM: (crmId: string) => Promise<void>;
  setActiveEntityByName: (entityName: string) => void;
  setActiveCRM: (crm: CRMSummary | null) => void;
}

const CRMContext = createContext<CRMContextType | undefined>(undefined);

const SELECTED_CRM_KEY = 'aura_selected_crm_id';

export const CRMProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [crms, setCrms] = useState<CRMSummary[]>([]);
  const [activeCRM, setActiveCRM] = useState<CRMSummary | null>(null);
  const [activeEntityName, setActiveEntityName] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const refreshCRMs = useCallback(async () => {
    if (!user) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.listCRMs(50, 0);
      setCrms(res.items);

      if (res.items.length === 0) {
        setActiveCRM(null);
        setActiveEntityName(null);
        if (typeof localStorage !== 'undefined') {
          localStorage.removeItem(SELECTED_CRM_KEY);
        }
        return;
      }

      // Check stored selection from localStorage or current state
      const savedCrmId = typeof localStorage !== 'undefined' ? localStorage.getItem(SELECTED_CRM_KEY) : null;
      const targetCrm =
        (savedCrmId && res.items.find((c) => c.crm_id === savedCrmId)) ||
        (activeCRM && res.items.find((c) => c.crm_id === activeCRM.crm_id)) ||
        res.items[0];

      if (targetCrm) {
        setActiveCRM(targetCrm);
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem(SELECTED_CRM_KEY, targetCrm.crm_id);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load CRMs';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [user, activeCRM]);

  useEffect(() => {
    if (user) {
      refreshCRMs();
    } else {
      setCrms([]);
      setActiveCRM(null);
      setActiveEntityName(null);
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem(SELECTED_CRM_KEY);
      }
    }
  }, [user]);

  // Listen for CRM configuration changes from tools/schema editor
  useEffect(() => {
    const handleConfigChanged = () => {
      if (activeCRM?.crm_id) {
        selectCRM(activeCRM.crm_id);
      } else {
        refreshCRMs();
      }
    };
    window.addEventListener('crm-config-changed', handleConfigChanged);
    return () => {
      window.removeEventListener('crm-config-changed', handleConfigChanged);
    };
  }, [activeCRM?.crm_id, refreshCRMs]);

  // Set default active entity when activeCRM changes
  useEffect(() => {
    if (activeCRM?.configuration?.entities?.length) {
      if (!activeEntityName || !activeCRM.configuration.entities.some((e) => e.name === activeEntityName)) {
        setActiveEntityName(activeCRM.configuration.entities[0].name);
      }
    } else {
      setActiveEntityName(null);
    }
  }, [activeCRM, activeEntityName]);

  const selectCRM = async (crmId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const crm = await api.getCRM(crmId);
      setActiveCRM(crm);
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(SELECTED_CRM_KEY, crmId);
      }
      if (crm.configuration?.entities?.length > 0) {
        setActiveEntityName(crm.configuration.entities[0].name);
      }
      // Broadcast record change event so records and analytics views refresh immediately
      window.dispatchEvent(new CustomEvent('records-changed'));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch CRM details';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const setActiveEntityByName = (entityName: string) => {
    setActiveEntityName(entityName);
  };

  const activeEntity = activeCRM?.configuration?.entities?.find((e) => e.name === activeEntityName) ||
    activeCRM?.configuration?.entities?.[0] || null;

  return (
    <CRMContext.Provider
      value={{
        crms,
        activeCRM,
        activeEntity,
        isLoading,
        error,
        refreshCRMs,
        selectCRM,
        setActiveEntityByName,
        setActiveCRM,
      }}
    >
      {children}
    </CRMContext.Provider>
  );
};

export const useCRM = () => {
  const context = useContext(CRMContext);
  if (!context) {
    throw new Error('useCRM must be used within a CRMProvider');
  }
  return context;
};
