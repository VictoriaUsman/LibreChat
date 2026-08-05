import { useState, useCallback, useEffect, useRef } from 'react';
import { tourSteps } from './tourSteps';
import type { TourStep } from './tourSteps';

export type TourEndReason = 'finished' | 'dismissed' | 'no-anchors';

/** How often to re-check for a step's anchor while it hasn't appeared yet. */
export const ANCHOR_RETRY_INTERVAL_MS = 250;
/** How many retries to allow before concluding an anchor is genuinely absent (not just not
 * yet rendered) — ~10s total, comfortably longer than a real page's composer/sidebar can take
 * to finish mounting after a fresh load (conversation/config data has to resolve first). */
export const ANCHOR_RETRY_MAX_ATTEMPTS = 40;
/** Retries allowed once the tour is already running. The long window above exists for the
 * cold-load race, where the composer may still be mounting; by the time a step has been shown
 * the app is up, so an anchor that isn't there is genuinely absent rather than late. Waiting
 * the full 10s in that case just strands the user on a step that will never render. */
export const ANCHOR_RETRY_MAX_ATTEMPTS_MID_TOUR = 12;
/** Ceiling on anchor hunting across the whole tour, ~12s. The per-step windows are each
 * defensible, but they compound: if nothing ever mounts, four steps at the cold-start window
 * would spend ~40s holding a full-screen click blocker that is invisible in dark mode, with no
 * popover to explain it and Tab hard-blocked. Past this budget the tour gives up. */
export const ANCHOR_RETRY_MAX_TOTAL_ATTEMPTS = 48;

interface UseGuidedTourResult {
  currentStep: TourStep | null;
  stepIndex: number;
  totalSteps: number;
  isFirstStep: boolean;
  isLastStep: boolean;
  next: () => void;
  back: () => void;
  dismiss: () => void;
}

export default function useGuidedTour(onEnd: (reason: TourEndReason) => void): UseGuidedTourResult {
  const [stepIndex, setStepIndex] = useState(0);
  const [currentStep, setCurrentStep] = useState<TourStep | null>(null);
  const shownAnyStep = useRef(false);
  const totalAttempts = useRef(0);
  /** +1 forward, -1 backward — which way to skip a step whose anchor never appears. */
  const direction = useRef<1 | -1>(1);

  // Retries the anchor lookup for the current step instead of checking once: on a real page
  // load, the sidebar/composer render at different times as conversation/config data resolves
  // (measured 3-5s apart in practice), so a single synchronous check reliably concludes an
  // anchor is "missing" before it has actually mounted — permanently skipping that step for
  // every real user. Only after exhausting the retry window is a step treated as genuinely
  // absent (e.g. hidden by RBAC) and skipped.
  useEffect(() => {
    const rawStep = stepIndex < tourSteps.length ? tourSteps[stepIndex] : null;
    if (rawStep == null) {
      return;
    }

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const maxAttempts = shownAnyStep.current
      ? ANCHOR_RETRY_MAX_ATTEMPTS_MID_TOUR
      : ANCHOR_RETRY_MAX_ATTEMPTS;

    // Drop the outgoing step before hunting for the new one. Without this, `currentStep` keeps
    // pointing at the PREVIOUS step for the whole retry window while `stepIndex` has already
    // advanced — so the popover renders the previous step's text at the previous step's anchor
    // while the footer counts up. That is the "step 3 points at the chat toggles" bug: step 2's
    // popover, on the Tools button, carrying the *next* step's number, for up to the full timeout.
    //
    // On a normal transition this costs nothing: `check()` runs synchronously below and finds
    // the anchor in the same effect, so React batches both updates into one render and no blank
    // frame is ever committed.
    setCurrentStep(null);

    const check = () => {
      if (cancelled) {
        return;
      }
      if (document.querySelector(rawStep.anchorSelector) != null) {
        shownAnyStep.current = true;
        // The budget below guards *consecutive* failure. Reset on every success, or normal use —
        // stepping back over a permanently missing step, say — slowly drains it and ends the tour
        // for someone whose app is working fine.
        totalAttempts.current = 0;
        setCurrentStep(rawStep);
        return;
      }
      attempts += 1;
      totalAttempts.current += 1;
      // Give up entirely once the whole-tour budget is spent, rather than skipping to a step
      // that will almost certainly be missing too. Ending is the safe direction: it tears the
      // backdrop down instead of leaving an invisible blocker up for the sum of every window.
      if (totalAttempts.current >= ANCHOR_RETRY_MAX_TOTAL_ATTEMPTS) {
        setCurrentStep(null);
        onEnd(shownAnyStep.current ? 'finished' : 'no-anchors');
        return;
      }
      if (attempts >= maxAttempts) {
        setCurrentStep(null);
        // Skip in the direction the user was travelling. Always incrementing made Back a one-way
        // valve: pressing it onto a missing step blanked the popover, then bounced forward to the
        // step just left, with no way past it.
        if (direction.current === -1 && stepIndex > 0) {
          setStepIndex((prev) => Math.max(0, prev - 1));
        } else if (stepIndex + 1 >= tourSteps.length) {
          onEnd(shownAnyStep.current ? 'finished' : 'no-anchors');
        } else {
          setStepIndex((prev) => prev + 1);
        }
        return;
      }
      timeoutId = setTimeout(check, ANCHOR_RETRY_INTERVAL_MS);
    };

    check();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
    // `[stepIndex]` only, and the disable below is load-bearing rather than lazy. `onEnd` is not
    // stable — it closes over `markSeen` from `useLocalStorage`, which returns a fresh setter
    // every render — so listing it would restart this effect on every render, resetting
    // `attempts` to 0 each time. A missing anchor would then retry forever, holding an invisible
    // backdrop with no popover and no exit. Keep the dep list as-is.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepIndex]);

  const advanceOrEnd = useCallback(
    (reasonIfDone: TourEndReason) => {
      if (stepIndex + 1 >= tourSteps.length) {
        onEnd(reasonIfDone);
      } else {
        setStepIndex((prev) => prev + 1);
      }
    },
    [stepIndex, onEnd],
  );

  const next = useCallback(() => {
    direction.current = 1;
    advanceOrEnd('finished');
  }, [advanceOrEnd]);

  const back = useCallback(() => {
    direction.current = -1;
    setStepIndex((prev) => Math.max(0, prev - 1));
  }, []);

  const dismiss = useCallback(() => onEnd('dismissed'), [onEnd]);

  return {
    currentStep,
    stepIndex,
    totalSteps: tourSteps.length,
    isFirstStep: stepIndex === 0,
    isLastStep: stepIndex >= tourSteps.length - 1,
    next,
    back,
    dismiss,
  };
}
