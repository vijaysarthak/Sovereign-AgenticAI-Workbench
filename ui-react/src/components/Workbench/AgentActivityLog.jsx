import React, { useEffect, useRef, useState } from 'react';
import {
  Activity, GitBranch, Search, PenLine, ShieldCheck, Info, Code, Terminal, Eye,
  FileSearch, FileSignature, CheckCircle2, XCircle, Loader2, Trash2, Cpu, Play,
} from 'lucide-react';
import { useModelStatus } from '../../contexts/ModelContext';

// Which agent runs each backend stage (harness/runner.py, code_runner.py,
// approval_note.py). `role` = the configured model role it uses;
// `engine` = a deterministic step that involves no LLM at all.
const STAGES = {
  intent: { agent: 'Intent Router', role: 'primary', icon: GitBranch },
  extraction: { agent: 'Document Parser', engine: 'text & image extraction', icon: FileSearch },
  retrieval: { agent: 'Retrieval Engine', engine: 'document search + security gate', icon: Search },
  drafting: { agent: 'Drafting Agent', role: 'primary', icon: PenLine },
  verification: { agent: 'Citation Verifier', engine: 'exact text match', icon: ShieldCheck },
  capability: { agent: 'Capability Agent', role: 'primary', icon: Info },
  code_drafting: { agent: 'Code Agent', role: 'code', icon: Code },
  code_execution: { agent: 'Python Sandbox', engine: 'isolated subprocess', icon: Terminal },
  vision: { agent: 'Vision Agent', role: 'vision', icon: Eye },
  approval_note_drafting: { agent: 'Findings Agent', role: 'primary', icon: FileSearch },
  approval_note_synthesis: { agent: 'Approval Note Agent', role: 'primary', icon: FileSignature },
  final: { agent: 'Pipeline', icon: CheckCircle2 },
  error: { agent: 'Pipeline', icon: XCircle },
};

const ROUTES = {
  content: 'document question → search corpus, draft, verify citations',
  code: 'coding request → Code Agent + Python sandbox',
  capability: 'question about the assistant → capability answer',
  other: 'not a real question → no drafting',
};

function describe(ev) {
  const attempt = ev.attempt ? `Attempt ${ev.attempt}${ev.max_attempts ? `/${ev.max_attempts}` : ''}: ` : '';
  switch (`${ev.stage}:${ev.status || ''}`) {
    case 'intent:start': return ['Classifying what kind of request this is', 'running'];
    case 'intent:done':
      return ev.fallback
        ? [`Classifier model gave no usable answer — routed by keyword rules as "${ev.category}" — ${ROUTES[ev.category] || 'processing'}`, 'fail']
        : [`Routed as "${ev.category}" — ${ROUTES[ev.category] || 'processing'}`, 'ok'];
    case 'extraction:done': return [
      `Extracted ${ev.text_chunks} text page(s) and ${ev.images} image(s) from ${ev.filename}`, 'ok',
    ];
    case 'retrieval:start': return [`Searching the document corpus (${ev.mode || 'lexical'})`, 'running'];
    case 'retrieval:done': return [
      `Found ${ev.passages_found} readable passage(s); ${ev.denials_found} document(s) withheld by the security gate`,
      ev.passages_found > 0 ? 'ok' : 'fail',
    ];
    case 'drafting:start': return [`${attempt}writing an answer from the passages`, 'running'];
    case 'drafting:done': return [`${attempt}draft ready with ${ev.citations_claimed} citation(s)`, 'ok'];
    case 'drafting:error': return [`${attempt}drafting failed — ${ev.message}`, 'fail'];
    case 'verification:start': return [`${attempt}checking every quote against the source text`, 'running'];
    case 'verification:pass': return [`${attempt}all citations verified verbatim`, 'ok'];
    case 'verification:fail': return [`${attempt}rejected — ${ev.reason}`, 'fail'];
    case 'capability:start': return ['Answering from real system and access facts', 'running'];
    case 'capability:done': return ['Capability answer ready', 'ok'];
    case 'code_drafting:start': return [`${attempt}writing a Python script`, 'running'];
    case 'code_drafting:done': return [`${attempt}script ready`, 'ok'];
    case 'code_drafting:error': return [`${attempt}${ev.message}`, 'fail'];
    case 'code_execution:start': return [`${attempt}running the script in the sandbox`, 'running'];
    case 'code_execution:done': return [
      `${attempt}exit code ${ev.exit_code}${ev.timed_out ? ' (timed out)' : ''}`,
      ev.exit_code === 0 && !ev.timed_out ? 'ok' : 'fail',
    ];
    case 'vision:start': return [`Analyzing image ${ev.label}`, 'running'];
    case 'vision:done': return [`Described ${ev.label}`, 'ok'];
    case 'vision:error': return [`Could not analyze ${ev.label} — ${ev.message}`, 'fail'];
    case 'approval_note_drafting:start': return [`${attempt}extracting findings from the report`, 'running'];
    case 'approval_note_drafting:pass': return [`${attempt}findings verified verbatim`, 'ok'];
    case 'approval_note_drafting:fail': return [`${attempt}rejected — ${ev.reason}`, 'fail'];
    case 'approval_note_drafting:error': return [`${attempt}${ev.message}`, 'fail'];
    case 'approval_note_synthesis:start': return ['Writing title, summary and recommendation', 'running'];
    case 'approval_note_synthesis:done': return ['Approval note ready', 'ok'];
    default:
      if (ev.stage === 'final') {
        const r = ev.response || {};
        const cites = r.citations?.length || 0;
        return r.status === 'answered'
          ? [`Answered${cites ? ` with ${cites} verified citation(s)` : ''}`, 'ok']
          : ['Response withheld (abstained)', 'fail'];
      }
      if (ev.stage === 'error') return [ev.message || 'Request failed', 'fail'];
      return [`${ev.stage} ${ev.status || ''}`.trim(), 'info'];
  }
}

const TONE = {
  running: 'text-sov-orange',
  ok: 'text-sov-green',
  fail: 'text-sov-red',
  info: 'text-sov-text-secondary',
};

const clock = (ms) => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

export default function AgentActivityLog({ entries, isRunning, onClear }) {
  const { modelIdForRole } = useModelStatus();
  const scrollRef = useRef(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!isRunning) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [isRunning]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [entries.length]);

  const lastIndex = entries.length - 1;

  return (
    <div className="bg-sov-card border border-sov-border rounded-xl flex flex-col h-full">
      <div className="p-4 border-b border-sov-border-light flex items-center justify-between">
        <h3 className="text-lg font-semibold text-sov-text-primary flex items-center gap-2">
          <Activity size={18} className="text-sov-orange" />
          Live Agent Activity
          {isRunning && (
            <span className="relative flex h-2 w-2 ml-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sov-green opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-sov-green" />
            </span>
          )}
        </h3>
        <button
          onClick={onClear}
          disabled={isRunning || entries.length === 0}
          className="text-xs text-sov-text-muted hover:text-sov-text-primary flex items-center gap-1 disabled:opacity-30"
        >
          <Trash2 size={12} /> Clear
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 font-mono text-xs space-y-1">
        {entries.length === 0 && (
          <div className="h-full flex items-center justify-center text-center text-sov-text-muted font-sans text-sm px-6">
            No agent activity yet. Run a query to watch each step, the agent handling it, and the model it uses — live.
          </div>
        )}

        {entries.map((entry, index) => {
          if (entry.type === 'run') {
            return (
              <div key={entry.id} className={`flex items-start gap-2 px-2 py-2 rounded bg-sov-sidebar border border-sov-border-light ${index > 0 ? 'mt-3' : ''}`}>
                <Play size={12} className="text-sov-orange mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sov-text-primary break-words">{entry.label}</div>
                  {entry.detail && <div className="text-sov-text-muted break-words">{entry.detail}</div>}
                </div>
                <span className="text-sov-text-muted shrink-0">{clock(entry.at)}</span>
              </div>
            );
          }

          const ev = entry.event;
          const meta = STAGES[ev.stage] || { agent: ev.stage, icon: Info };
          const [text, tone] = describe(ev);
          const running = tone === 'running' && isRunning && index === lastIndex;
          const Icon = running ? Loader2 : meta.icon;
          const model = ev.model || (ev.stage === 'final' ? ev.response?.model_used : null);
          const expectedModel = !model && ev.status === 'start' && meta.role ? modelIdForRole(meta.role) : null;
          const elapsed = ((entry.at - entry.runStartedAt) / 1000).toFixed(1);

          return (
            <div key={entry.id} className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-sov-card-hover">
              <span className="text-sov-text-muted w-12 shrink-0 text-right">+{elapsed}s</span>
              <Icon size={13} className={`${TONE[tone]} mt-0.5 shrink-0 ${running ? 'animate-spin' : ''}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="text-sov-text-primary font-semibold">{meta.agent}</span>
                  {model && (
                    <span className="inline-flex items-center gap-1 px-1.5 rounded bg-sov-green/10 text-sov-green border border-sov-green/20">
                      <Cpu size={10} /> {model}
                    </span>
                  )}
                  {expectedModel && (
                    <span className="inline-flex items-center gap-1 px-1.5 rounded bg-sov-border text-sov-text-secondary" title="Configured model for this agent">
                      <Cpu size={10} /> {expectedModel}
                    </span>
                  )}
                  {meta.engine && (
                    <span className="px-1.5 rounded bg-sov-border text-sov-text-muted">no LLM · {meta.engine}</span>
                  )}
                </div>
                <div className={`${TONE[tone]} break-words font-sans text-[13px] leading-snug`}>
                  {text}
                  {running && <span className="text-sov-text-muted"> · {((now - entry.at) / 1000).toFixed(0)}s</span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
