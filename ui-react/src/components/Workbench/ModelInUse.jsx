import React from 'react';
import { Cpu } from 'lucide-react';
import { useModelStatus } from '../../contexts/ModelContext';

export default function ModelInUse() {
  const { models, modelsLoading, activeModelId, isProcessing, backend } = useModelStatus();

  return (
    <div className="bg-sov-card border border-sov-border rounded-xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sov-text-primary flex items-center gap-2">
          <Cpu size={18} className="text-sov-orange" />
          Model in Use
        </h3>
        <div className="flex items-center gap-1.5 px-2 py-0.5 bg-sov-green/10 border border-sov-green/20 rounded text-xs text-sov-green font-medium">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sov-green opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-sov-green"></span>
          </span>
          Live
        </div>
      </div>

      {isProcessing && (
        <div className="text-sov-orange text-sm mb-4 animate-pulse">
          Processing your query...
        </div>
      )}

      <div className="space-y-2 mb-4 bg-sov-sidebar p-3 rounded-lg border border-sov-border-light">
        {modelsLoading ? (
          <div className="text-xs text-sov-text-muted">Loading models...</div>
        ) : models.length === 0 ? (
          <div className="text-xs text-sov-text-muted">No models configured.</div>
        ) : (
          models.map(model => {
            const isActive = model.id === activeModelId;
            return (
              <div key={model.id} className="flex items-center gap-3 text-sm">
                <div className={`w-3 h-3 rounded-full border flex items-center justify-center ${
                  isActive ? 'border-sov-green' : 'border-sov-border'
                }`}>
                  {isActive && (
                    <span className="relative flex h-1.5 w-1.5">
                      {isProcessing && (
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sov-green opacity-75" />
                      )}
                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-sov-green" />
                    </span>
                  )}
                </div>
                <span className={`font-mono text-xs truncate ${
                  isActive ? 'text-sov-green' : 'text-sov-text-secondary'
                }`}>
                  {model.id}
                </span>
              </div>
            );
          })
        )}
      </div>

      <div className="text-xs border-t border-sov-border-light pt-3">
        <div className="text-sov-text-muted mb-1">
          Using: <span className="text-sov-green font-mono">{activeModelId || 'none yet'}</span>
        </div>
        <div className="text-sov-text-muted font-mono text-[10px] break-all">
          {backend === 'ollama' ? 'http://localhost:11434/api/chat' : `backend: ${backend || 'unknown'}`}
        </div>
      </div>
    </div>
  );
}
