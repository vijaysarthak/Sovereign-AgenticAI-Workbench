import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiGet } from '../api/client';
import { useAuth } from './AuthContext';

const ModelContext = createContext(null);

/**
 * Tracks which locally-configured Ollama model is actually driving the
 * current/most recent query, shared between WorkbenchPage (which knows,
 * turn by turn, what the backend is doing) and ModelsPage / ModelInUse
 * (which just display it). Backed by GET /models for the real configured +
 * installed model list, instead of a hardcoded array duplicated per page.
 */
export function ModelProvider({ children }) {
  const { principal } = useAuth();
  const [models, setModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [backend, setBackend] = useState(null);
  const [activeModelId, setActiveModelId] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const fetchModels = useCallback(async () => {
    try {
      setModelsLoading(true);
      const data = await apiGet('/models');
      setModels(data?.models || []);
      setBackend(data?.backend || null);
    } catch {
      setModels([]);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (principal) {
      fetchModels();
    } else {
      setModels([]);
      setModelsLoading(false);
    }
  }, [principal, fetchModels]);

  // Resolve a pipeline role (from a stream event's stage/category, e.g.
  // "code", "vision", "primary") to the model id configured for it, so
  // WorkbenchPage can highlight the right card the moment intent
  // classification (or the vision stage) tells us which path was taken --
  // before the final, authoritative `model_used` arrives on the response.
  const modelIdForRole = useCallback((role) => {
    const match = models.find((m) => m.roles?.includes(role));
    return match?.id || null;
  }, [models]);

  const value = {
    models,
    modelsLoading,
    backend,
    activeModelId,
    setActiveModelId,
    isProcessing,
    setIsProcessing,
    modelIdForRole,
    refetchModels: fetchModels,
  };

  return <ModelContext.Provider value={value}>{children}</ModelContext.Provider>;
}

export function useModelStatus() {
  const ctx = useContext(ModelContext);
  if (!ctx) throw new Error('useModelStatus must be used within ModelProvider');
  return ctx;
}
