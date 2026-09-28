import React from 'react';
import { Cpu, Server, Shield, CheckCircle, Circle, HelpCircle, XCircle } from 'lucide-react';
import { useModelStatus } from '../contexts/ModelContext';

const ROLE_LABELS = {
  primary: 'Primary Drafting',
  fallback: 'Fallback Drafting',
  code: 'Code',
  vision: 'Vision',
};

function formatSize(bytes) {
  if (!bytes) return null;
  const gb = bytes / (1024 ** 3);
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${(bytes / (1024 ** 2)).toFixed(0)} MB`;
}

const ModelsPage = () => {
  const { models, modelsLoading, backend, activeModelId, isProcessing } = useModelStatus();

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary overflow-y-auto">
      <div className="mb-6 flex items-center gap-3">
        <Cpu className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">Available Models</h1>
      </div>

      <div className="bg-sov-card border border-sov-border rounded-lg p-5 mb-8 flex flex-col md:flex-row gap-6 items-center">
        <div className="flex-1">
          <h2 className="text-lg font-semibold mb-2 flex items-center gap-2"><Server size={20} className="text-sov-text-secondary"/> Sovereign Infrastructure</h2>
          <p className="text-sov-text-secondary text-sm leading-relaxed">
            All models are deployed on-premise within the air-gapped environment. No data leaves the secure perimeter.
            Active backend: <span className="font-mono text-sov-orange bg-sov-orange/10 px-2 py-0.5 rounded ml-1">{backend || 'unknown'}</span>
          </p>
        </div>
        <div className="bg-sov-bg p-4 rounded-lg border border-sov-border flex items-center gap-3">
          <Shield className="text-sov-green" size={24} />
          <div>
            <div className="text-sm font-semibold text-sov-green">Fully Isolated</div>
            <div className="text-xs text-sov-text-muted">Zero External Telemetry</div>
          </div>
        </div>
      </div>

      <h3 className="text-lg font-semibold mb-4 text-sov-text-secondary">Configured Models</h3>

      {modelsLoading ? (
        <div className="text-sov-text-muted">Loading models...</div>
      ) : models.length === 0 ? (
        <div className="text-sov-text-muted">No models configured for this deployment.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {models.map(model => {
            const isActive = model.id === activeModelId;
            return (
              <div
                key={model.id}
                className={`p-5 rounded-lg border relative overflow-hidden group transition-colors ${
                  isActive ? 'border-sov-green bg-sov-card' : 'border-sov-border bg-sov-card'
                }`}
              >
                {isActive && (
                  <div className="absolute top-0 right-0 p-2 bg-sov-green text-black text-xs font-bold rounded-bl-lg flex items-center gap-1">
                    <span className="relative flex h-2 w-2">
                      {isProcessing && (
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-black opacity-60" />
                      )}
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-black" />
                    </span>
                    {isProcessing ? 'PROCESSING' : 'ACTIVE'}
                  </div>
                )}

                <div className="flex justify-between items-start mb-3 pr-16">
                  <h4 className="font-mono font-semibold text-lg break-all">{model.id}</h4>
                </div>

                <div className="flex flex-wrap gap-1.5 mb-3">
                  {model.roles.map((role) => (
                    <span key={role} className="px-2 py-1 text-xs rounded bg-sov-sidebar border border-sov-border text-sov-text-muted">
                      {ROLE_LABELS[role] || role}
                    </span>
                  ))}
                </div>

                <div className="flex items-center gap-2 text-sm mb-4">
                  {model.status === 'installed' ? (
                    <>
                      <CheckCircle className="text-sov-green" size={16} />
                      <span className="text-sov-green">Installed</span>
                    </>
                  ) : model.status === 'missing' ? (
                    <>
                      <XCircle className="text-sov-red" size={16} />
                      <span className="text-sov-red">Not pulled locally</span>
                    </>
                  ) : (
                    <>
                      <HelpCircle className="text-sov-text-muted" size={16} />
                      <span className="text-sov-text-muted">Status unknown</span>
                    </>
                  )}
                </div>

                <div className="pt-3 border-t border-sov-border flex justify-between items-center">
                  <span className={`w-3 h-3 rounded-full border flex items-center justify-center ${isActive ? 'border-sov-green' : 'border-sov-border'}`}>
                    {isActive && <span className="w-1.5 h-1.5 bg-sov-green rounded-full" />}
                  </span>
                  {model.size_bytes ? (
                    <span className="text-xs font-medium bg-sov-bg px-2 py-1 rounded">{formatSize(model.size_bytes)}</span>
                  ) : (
                    <Circle className="text-sov-text-muted" size={16} />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ModelsPage;
