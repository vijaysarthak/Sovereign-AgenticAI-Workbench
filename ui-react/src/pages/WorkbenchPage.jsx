import React, { useState, useEffect, useRef } from 'react';
import { Shield, AlertCircle } from 'lucide-react';
import PipelineSteps from '../components/Workbench/PipelineSteps';
import { initialProgress, startProgress, applyEvent, failProgress } from '../components/Workbench/pipelineProgress';
import QueryInput from '../components/Workbench/QueryInput';
import ResultsPanel from '../components/Workbench/ResultsPanel';
import AgentActivityLog from '../components/Workbench/AgentActivityLog';
import DocumentPreview from '../components/Workbench/DocumentPreview';
import SystemStatus from '../components/Workbench/SystemStatus';
import ModelInUse from '../components/Workbench/ModelInUse';
import { apiGet, apiStream } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useModelStatus } from '../contexts/ModelContext';

export default function WorkbenchPage() {
  const { principal } = useAuth();
  const { modelIdForRole, setActiveModelId, setIsProcessing } = useModelStatus();
  const [documents, setDocuments] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamEvents, setStreamEvents] = useState([]);
  const [currentResult, setCurrentResult] = useState(null);
  const [progress, setProgress] = useState(initialProgress);
  const [queryError, setQueryError] = useState(null);
  const [activityLog, setActivityLog] = useState([]);
  const logIdRef = useRef(0);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const data = await apiGet('/documents');
      setDocuments(data || []);
    } catch (error) {
      console.error('Failed to fetch documents', error);
    }
  };

  const [conversationId, setConversationId] = useState(null);

  // Session-long activity log (capped) so earlier runs stay visible above the current one.
  const appendLog = (entry) => {
    logIdRef.current += 1;
    setActivityLog(prev => [...prev, { id: logIdRef.current, at: Date.now(), ...entry }].slice(-300));
  };

  const runStream = async (url, body, run) => {
    setIsStreaming(true);
    setIsProcessing(true);
    setStreamEvents([]);
    setCurrentResult(null);
    setQueryError(null);
    setProgress(startProgress());

    const runStartedAt = Date.now();
    appendLog({ type: 'run', ...run });
    let finished = false;

    try {
      await apiStream(url, body, (event) => {
        setStreamEvents(prev => [...prev, event]);
        appendLog({ type: 'event', event, runStartedAt });
        if (event.stage === 'final' || event.stage === 'error') finished = true;

        setProgress(prev => applyEvent(prev, event));

        // As soon as intent routing (or a vision/code stage) tells us which
        // pipeline path was taken, glow the model that path uses -- ahead of
        // the final, authoritative model_used on the response, so the
        // Models page/sidebar reacts live instead of only at the very end.
        if (event.stage === 'intent' && event.status === 'done') {
          const role = event.category === 'code' ? 'code' : 'primary';
          const modelId = modelIdForRole(role);
          if (modelId) setActiveModelId(modelId);
        } else if (event.stage === 'vision' && event.status === 'start') {
          const modelId = modelIdForRole('vision');
          if (modelId) setActiveModelId(modelId);
        } else if (
          (event.stage === 'approval_note_drafting' || event.stage === 'drafting') && event.status === 'start'
        ) {
          const modelId = modelIdForRole('primary');
          if (modelId) setActiveModelId(modelId);
        }

        if (event.stage === 'final' && event.response) {
          setCurrentResult(event.response);
          setIsStreaming(false);
          setIsProcessing(false);
          if (event.response.conversation_id) {
            setConversationId(event.response.conversation_id);
          }
          // Authoritative: the model that actually produced this answer,
          // which may be a promoted fallback the intent-stage guess above
          // didn't know about.
          if (event.response.model_used) {
            setActiveModelId(event.response.model_used);
          }
        } else if (event.stage === 'error') {
          setIsStreaming(false);
          setIsProcessing(false);
          setQueryError(event.message || 'The query failed.');
        }
      });
      if (!finished) {
        throw new Error('The connection closed before the agent finished. Please try again.');
      }
    } catch (error) {
      console.error('Query failed:', error);
      setIsStreaming(false);
      setIsProcessing(false);
      setProgress(prev => failProgress(prev, error.message));
      setQueryError(error.message || 'The query failed. Please try again.');
      appendLog({ type: 'event', event: { stage: 'error', message: error.message }, runStartedAt });
    }
  };

  // Follow-up questions continue the same conversation so the backend's
  // short conversation memory (trust/conversations.py) can resolve "that",
  // "it", etc. -- and Generated Outputs groups them into one thread.
  const handleQuerySubmit = (question, uploadId, fileName) => runStream('/ask/stream', {
    question,
    top_k: 5,
    ...(uploadId && { upload_id: uploadId }),
    ...(conversationId && { conversation_id: conversationId }),
  }, {
    label: `Question: "${question}"`,
    detail: [
      uploadId && `Attached file: ${fileName}`,
      conversationId && 'Follow-up in the current conversation',
    ].filter(Boolean).join(' · '),
  });

  const handleApprovalNote = (uploadId, fileName) => runStream('/ask/approval-note/stream', {
    upload_id: uploadId,
    ...(conversationId && { conversation_id: conversationId }),
  }, {
    label: `Approval note requested for "${fileName}"`,
    detail: 'Findings extraction → verification → note drafting',
  });

  const startNewConversation = () => {
    setConversationId(null);
    setCurrentResult(null);
    setStreamEvents([]);
    setQueryError(null);
  };

  return (
    <div className="flex h-full bg-sov-bg text-sov-text-primary overflow-hidden w-full">
      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full overflow-y-auto custom-scrollbar">
        <div className="p-8 max-w-6xl mx-auto w-full">
          
          <div className="mb-10 text-center">
            <h1 className="text-4xl font-bold mb-3 tracking-tight">
              From Documents to <span className="text-transparent bg-clip-text bg-gradient-to-r from-sov-orange to-sov-orange-dark">Decisions</span>
            </h1>
            <p className="text-sov-text-secondary text-lg">
              Upload, analyze, and generate with your on-premise AI agents.
            </p>
          </div>

          <PipelineSteps progress={progress} />
          
          <div className="mb-8">
            {conversationId && (
              <div className="flex items-center justify-between mb-2 text-xs text-sov-text-muted">
                <span>Continuing current conversation — follow-up questions keep context.</span>
                <button
                  onClick={startNewConversation}
                  disabled={isStreaming}
                  className="text-sov-orange hover:text-sov-orange-dark font-medium disabled:opacity-50"
                >
                  + New conversation
                </button>
              </div>
            )}
            <QueryInput
              onSubmit={handleQuerySubmit}
              onApprovalNote={handleApprovalNote}
              disabled={isStreaming}
              loading={isStreaming}
            />
          </div>

          {queryError && (
            <div className="mt-6 p-4 bg-sov-red/10 border border-sov-red/20 rounded-xl flex items-start gap-3 text-sov-red text-sm">
              <AlertCircle className="shrink-0 mt-0.5" size={18} />
              <span>{queryError}</span>
            </div>
          )}

          <ResultsPanel
            result={currentResult}
            streamEvents={streamEvents}
            isStreaming={isStreaming}
          />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
            <div className="lg:col-span-2 h-[500px]">
              <AgentActivityLog
                entries={activityLog}
                isRunning={isStreaming}
                onClear={() => setActivityLog([])}
              />
            </div>
            <div className="lg:col-span-1 h-[500px]">
              <DocumentPreview 
                document={null} // Pass selected document here when implemented
                citations={currentResult?.citations || []} 
              />
            </div>
          </div>
          
        </div>
      </div>

      {/* Right Sidebar */}
      <div className="w-80 bg-sov-sidebar border-l border-sov-border-light p-6 overflow-y-auto">
        <SystemStatus documentCount={documents.length} />
        
        <ModelInUse />

        <div className="bg-sov-card border border-sov-border rounded-xl p-5 relative overflow-hidden group hover:border-sov-orange/50 transition-colors">
          <div className="absolute top-0 right-0 w-24 h-24 bg-sov-orange/10 rounded-bl-full blur-2xl z-0 group-hover:bg-sov-orange/20 transition-colors" />
          <div className="relative z-10">
            <Shield className="text-sov-orange mb-3" size={24} />
            <h3 className="font-semibold text-sov-text-primary mb-1">Your data stays with you</h3>
            <p className="text-sm text-sov-text-secondary mb-4">On-premise. Air-gapped. Secure.</p>
            <button className="text-sm text-sov-orange hover:text-sov-orange-dark font-medium flex items-center gap-1 transition-colors">
              Learn more →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
