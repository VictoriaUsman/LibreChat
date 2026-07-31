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

    const check = () => {
      if (cancelled) {
        return;
      }
      if (document.querySelector(rawStep.anchorSelector) != null) {
        shownAnyStep.current = true;
        setCurrentStep(rawStep);
        return;
      }
      attempts += 1;
      if (attempts >= ANCHOR_RETRY_MAX_ATTEMPTS) {
        setCurrentStep(null);
        if (stepIndex + 1 >= tourSteps.length) {
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

  const next = useCallback(() => advanceOrEnd('finished'), [advanceOrEnd]);

  const back = useCallback(() => {
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
