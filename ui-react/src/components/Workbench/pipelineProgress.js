// Maps the backend's live stage events onto the four Workbench steps.
// Step states: 'pending' | 'active' | 'done' | 'skipped' | 'failed'.

export const STEPS = [
  { title: 'Scan', idle: 'Read the request' },
  { title: 'Extract', idle: 'Find key information' },
  { title: 'Consult', idle: 'Use on-premise models' },
  { title: 'Draft', idle: 'Generate output' },
];

// Every stage emitted by harness/runner.py, code_runner.py and approval_note.py.
const STAGE_TO_STEP = {
  intent: 0,
  extraction: 1,
  retrieval: 1,
  drafting: 2,
  code_drafting: 2,
  capability: 2,
  vision: 2,
  approval_note_drafting: 2,
  approval_note_synthesis: 2,
  verification: 3,
  code_execution: 3,
};

export function initialProgress() {
  return { runId: 0, states: STEPS.map(() => 'pending'), details: STEPS.map(() => ''), lastFailed: false };
}

export function startProgress() {
  const p = initialProgress();
  p.runId = Date.now();
  p.states[0] = 'active';
  p.details[0] = 'Sending request';
  return p;
}

function isFailure(ev) {
  if (ev.status === 'fail' || ev.status === 'error') return true;
  if (ev.stage === 'retrieval' && ev.status === 'done') return ev.passages_found === 0;
  if (ev.stage === 'code_execution' && ev.status === 'done') return ev.exit_code !== 0 || ev.timed_out;
  return false;
}

function detailFor(ev) {
  const attempt = ev.attempt > 1 ? ` (attempt ${ev.attempt})` : '';
  switch (`${ev.stage}:${ev.status}`) {
    case 'intent:start': return 'Classifying the request';
    case 'intent:done': return `Routed as ${ev.category}`;
    case 'extraction:done': return `${ev.text_chunks} text page(s), ${ev.images} image(s)`;
    case 'retrieval:start': return `Searching documents (${ev.mode || 'lexical'})`;
    case 'retrieval:done': return `${ev.passages_found} passage(s) found, ${ev.denials_found} withheld`;
    case 'drafting:start': return `Model writing answer${attempt}`;
    case 'drafting:done': return `Draft with ${ev.citations_claimed} citation(s)`;
    case 'drafting:error': return `Model call failed${attempt}`;
    case 'code_drafting:start': return `Code model writing script${attempt}`;
    case 'code_drafting:done': return 'Script ready';
    case 'code_drafting:error': return 'Script rejected, retrying';
    case 'capability:start': return 'Answering from system facts';
    case 'capability:done': return 'Answer ready';
    case 'vision:start': return 'Vision model reading image';
    case 'vision:done': return 'Image read';
    case 'vision:error': return 'Could not read image';
    case 'approval_note_drafting:start': return `Extracting findings${attempt}`;
    case 'approval_note_drafting:pass': return 'Findings verified';
    case 'approval_note_drafting:fail': return 'Findings rejected, retrying';
    case 'approval_note_drafting:error': return 'Model call failed';
    case 'approval_note_synthesis:start': return 'Writing the approval note';
    case 'approval_note_synthesis:done': return 'Note written';
    case 'verification:start': return `Checking citations${attempt}`;
    case 'verification:pass': return 'Citations verified';
    case 'verification:fail': return 'Citation rejected';
    case 'code_execution:start': return `Running script${attempt}`;
    case 'code_execution:done':
      return ev.exit_code === 0 && !ev.timed_out ? 'Script ran successfully' : `Script failed (exit ${ev.exit_code})`;
    default: return '';
  }
}

export function applyEvent(progress, ev) {
  if (ev.stage === 'final') return finishProgress(progress, ev.response?.status === 'answered');
  if (ev.stage === 'error') return failProgress(progress, ev.message);

  const target = STAGE_TO_STEP[ev.stage];
  if (target === undefined) return progress;

  const states = [...progress.states];
  const details = [...progress.details];
  const current = states.indexOf('active');

  if (target > current) {
    // Moving forward: the step we leave is done. A step this request doesn't
    // need (e.g. document search for a coding request) is complete too --
    // ticked, with "Not needed" -- rather than shown as skipped.
    for (let i = 0; i < target; i++) {
      if (states[i] === 'active') {
        states[i] = 'done';
        if (details[i] === 'Sending request') details[i] = 'Request received';
      } else if (states[i] === 'pending') {
        states[i] = 'done';
        details[i] = 'Not needed';
      }
    }
  } else if (target < current) {
    // A retry (e.g. citation rejected -> model drafts again) genuinely goes back a step.
    for (let i = target + 1; i < states.length; i++) {
      if (states[i] !== 'skipped') {
        states[i] = 'pending';
        details[i] = '';
      }
    }
  }
  states[target] = 'active';
  details[target] = detailFor(ev) || details[target];
  return { runId: progress.runId, states, details, lastFailed: isFailure(ev) };
}

export function finishProgress(progress, answered) {
  const states = [...progress.states];
  const details = [...progress.details];
  const active = states.indexOf('active');
  if (active !== -1) {
    states[active] = !answered && progress.lastFailed ? 'failed' : 'done';
  }
  const last = states.length - 1;
  if (answered && states[last] === 'pending') {
    states[last] = 'done';
    details[last] = 'Answer generated';
  }
  // Answered: every step is complete. Withheld: steps after the stopping point
  // genuinely never ran, so they stay visibly skipped.
  for (let i = 0; i < states.length; i++) {
    if (states[i] === 'pending') {
      states[i] = answered ? 'done' : 'skipped';
      details[i] = answered ? 'Not needed' : 'Not reached';
    }
  }
  if (!answered && states[last] === 'skipped') details[last] = 'Response withheld';
  return { runId: progress.runId, states, details, lastFailed: false };
}

export function failProgress(progress, message) {
  const states = [...progress.states];
  const details = [...progress.details];
  const active = states.indexOf('active');
  const index = active !== -1 ? active : 0;
  states[index] = 'failed';
  details[index] = message ? String(message).slice(0, 60) : 'Request failed';
  return { runId: progress.runId, states, details, lastFailed: true };
}

// The backend often finishes several steps within milliseconds of each other,
// which would make ticks appear at the same time or out of order. The UI
// instead replays progress one change at a time, in step order: a step becomes
// active, then gets its tick, then the next step starts.
export const STEP_DWELL_MS = 600;

// Returns the next displayed progress on the way to `target`, or null when the
// display has caught up. `stateChanged` is false for detail-text-only updates,
// which are applied immediately without waiting.
export function stepToward(displayed, target) {
  if (displayed.runId !== target.runId) return { next: target, stateChanged: true };

  const details = [...displayed.details];
  let detailsChanged = false;
  for (let i = 0; i < target.states.length; i++) {
    const current = displayed.states[i];
    const wanted = target.states[i];
    if (current === wanted) {
      if (details[i] !== target.details[i]) {
        details[i] = target.details[i];
        detailsChanged = true;
      }
      continue;
    }
    const states = [...displayed.states];
    // A step is always shown running before it is ticked or marked failed.
    states[i] = current === 'pending' && (wanted === 'done' || wanted === 'failed') ? 'active' : wanted;
    details[i] = target.details[i];
    return { next: { ...displayed, states, details }, stateChanged: true };
  }
  return detailsChanged ? { next: { ...displayed, details }, stateChanged: false } : null;
}
