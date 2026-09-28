import React, { useEffect, useRef, useState } from 'react';
import { Check, X, Minus } from 'lucide-react';
import { STEPS, STEP_DWELL_MS, initialProgress, stepToward } from './pipelineProgress';

const CIRCLE = {
  pending: 'bg-sov-card border-2 border-sov-border-light text-sov-text-secondary',
  active: 'bg-sov-orange text-sov-bg shadow-[0_0_15px_rgba(249,115,22,0.5)] scale-110',
  done: 'bg-sov-orange text-sov-bg',
  // Solid background: a translucent circle let the connector line show through it.
  skipped: 'bg-sov-card border-2 border-dashed border-sov-text-muted text-sov-text-secondary',
  failed: 'bg-sov-red text-white',
};

const TITLE = {
  pending: 'text-sov-text-primary',
  active: 'text-sov-orange',
  done: 'text-sov-text-primary',
  skipped: 'text-sov-text-muted',
  failed: 'text-sov-red',
};

export default function PipelineSteps({ progress = initialProgress() }) {
  // `progress` is where the backend actually is; `shown` replays it one step
  // change at a time so Scan -> Extract -> Consult -> Draft always tick in order.
  const [shown, setShown] = useState(progress);
  const lastTransitionAt = useRef(0);

  useEffect(() => {
    const step = stepToward(shown, progress);
    if (!step) return undefined;
    if (!step.stateChanged) {
      setShown(step.next);
      return undefined;
    }
    const wait = Math.max(0, STEP_DWELL_MS - (Date.now() - lastTransitionAt.current));
    const timer = setTimeout(() => {
      lastTransitionAt.current = Date.now();
      setShown(step.next);
    }, shown.runId !== progress.runId ? 0 : wait);
    return () => clearTimeout(timer);
  }, [progress, shown]);

  const { states, details } = shown;
  // The line fills up to the last step that actually ran, never through skipped ones.
  const reached = states.reduce((last, s, i) => (s === 'pending' || s === 'skipped' ? last : i), -1);
  const fill = reached > 0 ? (reached / (STEPS.length - 1)) * 100 : 0;

  return (
    <div className="w-full pt-8 pb-24">
      <div className="flex items-center justify-between relative max-w-4xl mx-auto">
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-full h-[2px] bg-sov-border-light z-0">
          <div className="h-full bg-sov-orange transition-all duration-500 ease-in-out" style={{ width: `${fill}%` }} />
        </div>

        {STEPS.map((step, index) => {
          const state = states[index];
          return (
            <div key={step.title} className="relative z-10 flex flex-col items-center group">
              {state === 'active' && (
                <span className="absolute inset-0 w-12 h-12 rounded-full bg-sov-orange/40 animate-ping" />
              )}
              <div
                className={`relative w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold transition-all duration-300 ${CIRCLE[state]}`}
                title={state === 'skipped' ? 'Skipped — not part of this request' : undefined}
              >
                {state === 'done' ? <Check size={20} strokeWidth={3} />
                  : state === 'failed' ? <X size={20} strokeWidth={3} />
                  : state === 'skipped' ? <Minus size={18} />
                  : index + 1}
              </div>

              <div className="mt-4 text-center absolute top-14 w-36 left-1/2 -translate-x-1/2">
                <div className={`font-semibold ${TITLE[state]}`}>{step.title}</div>
                <div className={`text-xs mt-1 line-clamp-2 ${state === 'active' ? 'text-sov-text-secondary' : 'text-sov-text-muted'}`}>
                  {details[index] || step.idle}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
