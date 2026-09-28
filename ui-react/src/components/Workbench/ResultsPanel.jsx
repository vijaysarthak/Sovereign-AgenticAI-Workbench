import React from 'react';
import { Loader2, CheckCircle, AlertTriangle, Download, Code, Shield, FileText, Presentation, Table } from 'lucide-react';

function renderMarkdown(text) {
  if (!text) return { __html: '' };
  
  let html = text
    .replace(/```([\s\S]*?)```/g, '<pre class="bg-sov-sidebar p-4 rounded-lg my-4 overflow-x-auto border border-sov-border text-sm font-mono text-sov-text-primary">$1</pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-sov-border px-1.5 py-0.5 rounded text-sov-orange font-mono text-sm">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-sov-text-primary font-bold">$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em class="text-sov-text-primary italic">$1</em>')
    .replace(/^### (.*$)/gim, '<h3 class="text-lg font-bold text-sov-text-primary mt-6 mb-2">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold text-sov-text-primary mt-8 mb-3">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold text-sov-orange mt-8 mb-4">$1</h1>')
    .replace(/^\> (.*$)/gim, '<blockquote class="border-l-4 border-sov-orange pl-4 py-1 my-4 text-sov-text-secondary bg-sov-sidebar/50 rounded-r">$1</blockquote>')
    .replace(/\n\n/g, '</p><p class="my-3">')
    .replace(/^- (.*$)/gim, '<li class="ml-4 list-disc marker:text-sov-orange my-1">$1</li>');

  html = `<p class="my-3">${html}</p>`;
  
  return { __html: html };
}

export default function ResultsPanel({ result, streamEvents, isStreaming }) {
  if (!result && !isStreaming) return null;

  const currentStage = streamEvents[streamEvents.length - 1]?.stage;

  return (
    <div className="bg-sov-card border border-sov-border rounded-xl p-6 mt-6 shadow-lg">
      
      {/* Streaming Progress Indicator */}
      {isStreaming && !result && (
        <div className="mb-6 pb-6 border-b border-sov-border-light">
          <div className="flex items-center gap-3 text-sov-orange mb-2">
            <Loader2 className="animate-spin" size={20} />
            <span className="font-medium capitalize text-lg">
              {currentStage || 'Processing'}...
            </span>
          </div>
          <div className="text-sm text-sov-text-muted pl-8">
            Analyzing context and compiling information.
          </div>
        </div>
      )}

      {/* Results Content */}
      {result && (
        <div className="space-y-8">
          
          {/* Header Status */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {result.status === 'answered' ? (
                <div className="flex items-center gap-2 bg-sov-green/10 text-sov-green px-3 py-1 rounded-full text-sm font-medium border border-sov-green/20">
                  <CheckCircle size={16} />
                  Answered
                </div>
              ) : (
                <div className="flex items-center gap-2 bg-sov-amber/10 text-sov-amber px-3 py-1 rounded-full text-sm font-medium border border-sov-amber/20">
                  <AlertTriangle size={16} />
                  Abstained
                </div>
              )}
              
              {result.effective_label && (
                <div className="flex items-center gap-2 bg-sov-border px-3 py-1 rounded-full text-sm font-medium text-sov-text-secondary border border-sov-border-light">
                  <Shield size={14} />
                  Tier {result.effective_label.tier}
                  {result.effective_label.compartments?.length > 0 && 
                    ` • ${result.effective_label.compartments.join(', ')}`}
                </div>
              )}
            </div>
            
            {result.status === 'answered' && result.ledger_row_id != null && (
              <div className="flex gap-2">
                {['DOCX', 'PPTX', 'XLSX'].map((format) => (
                  <a
                    key={format}
                    href={`/report/${result.ledger_row_id}?format=${format.toLowerCase()}`}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-sov-text-secondary bg-sov-sidebar hover:bg-sov-border hover:text-sov-text-primary rounded border border-sov-border-light transition-colors"
                  >
                    <Download size={14} />
                    {format}
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Main Answer */}
          <div className="text-sov-text-secondary leading-relaxed max-w-none">
            <div dangerouslySetInnerHTML={renderMarkdown(result.answer || '')} />
          </div>

          {/* Approval Note */}
          {result.approval_note && (
            <div className="bg-sov-sidebar rounded-lg p-5 border border-sov-border-light">
              <div className="flex items-center justify-between gap-3 mb-4">
                <h3 className="text-lg font-semibold text-sov-text-primary flex items-center gap-2">
                  <FileText size={18} className="text-sov-orange" />
                  {result.approval_note.title || 'Approval Note'}
                </h3>
                {result.ledger_row_id != null && (
                  <a
                    href={`/report/${result.ledger_row_id}/approval-note`}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-sov-orange bg-sov-card hover:bg-sov-border rounded border border-sov-orange/40 transition-colors"
                  >
                    <Download size={14} />
                    Approval Note (DOCX)
                  </a>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-sov-text-muted mb-1 text-xs uppercase tracking-wider">Summary</div>
                  <div className="text-sov-text-secondary">{result.approval_note.summary}</div>
                </div>
                <div>
                  <div className="text-sov-text-muted mb-1 text-xs uppercase tracking-wider">Recommendation</div>
                  <div className="text-sov-text-primary font-medium">{result.approval_note.recommendation}</div>
                </div>
              </div>
              <div className="mt-4 flex gap-4 text-xs text-sov-text-muted">
                <span>{result.approval_note.verified_findings?.length || 0} verified findings</span>
                <span>{result.approval_note.visual_observations?.length || 0} visual observations (unverified)</span>
              </div>
            </div>
          )}

          {/* Code Execution */}
          {result.code_execution && (
            <div className="bg-black rounded-lg overflow-hidden border border-sov-border-light">
              <div className="bg-sov-sidebar px-4 py-2 border-b border-sov-border-light flex justify-between items-center text-sm">
                <div className="flex items-center gap-2 text-sov-text-primary">
                  <Code size={16} className="text-sov-orange" />
                  Code Execution
                </div>
                <div className="text-sov-text-muted font-mono text-xs">
                  {Math.round((result.code_execution.duration_seconds || 0) * 1000)}ms • Exit {result.code_execution.exit_code}
                  {result.code_execution.timed_out && ' • Timed out'}
                </div>
              </div>
              <div className="p-4 font-mono text-sm overflow-x-auto text-sov-text-secondary">
                <pre>{result.code}</pre>
                {result.code_execution.stdout && (
                  <div className="mt-4 pt-4 border-t border-sov-border-light/30 text-sov-green">
                    {result.code_execution.stdout}
                  </div>
                )}
                {result.code_execution.stderr && (
                  <div className="mt-2 text-sov-red">
                    {result.code_execution.stderr}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Citations */}
          {result.citations && result.citations.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-sov-text-primary uppercase tracking-wider mb-3">Sources</h4>
              <div className="grid grid-cols-1 gap-3">
                {result.citations.map((cite, idx) => (
                  <div key={idx} className="bg-sov-sidebar border border-sov-border-light p-3 rounded-lg flex flex-col gap-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sov-orange font-mono text-xs">{cite.doc_id}</span>
                      <span className="text-sov-text-muted text-xs">Page {cite.page}</span>
                    </div>
                    <div className="text-sov-text-secondary text-sm italic border-l-2 border-sov-border pl-3">
                      "{cite.quote}"
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Denials */}
          {result.denials && result.denials.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-sov-red uppercase tracking-wider mb-3">Access Denied</h4>
              <div className="grid grid-cols-1 gap-3">
                {result.denials.map((denial, idx) => (
                  <div key={idx} className="bg-sov-red/5 border border-sov-red/20 p-3 rounded-lg">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-sov-red font-mono text-xs">{denial.doc_id}</span>
                      <span className="bg-sov-red/10 text-sov-red px-2 py-0.5 rounded text-xs">
                        Requires Tier {denial.required_label?.tier}
                      </span>
                    </div>
                    <div className="text-sov-text-secondary text-sm">
                      {denial.reason}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
}
