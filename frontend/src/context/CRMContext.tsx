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
      // If there's an active CRM, update it with fresh data
      if (activeCRM) {
        const updated = res.items.find((c) => c.crm_id === activeCRM.crm_id);
        if (updated) setActiveCRM(updated);
      } else if (res.items.length > 0) {
        // Automatically select the first CRM if none is selected
        setActiveCRM(res.items[0]);
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
    }
  }, [user]);

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
    try {
      const crm = await api.getCRM(crmId);
      setActiveCRM(crm);
      if (crm.configuration.entities.length > 0) {
        setActiveEntityName(crm.configuration.entities[0].name);
      }
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
