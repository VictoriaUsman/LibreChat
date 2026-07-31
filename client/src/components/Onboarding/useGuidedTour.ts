import { useState, useCallback, useLayoutEffect, useRef } from 'react';
import { tourSteps } from './tourSteps';
import type { TourStep } from './tourSteps';

export type TourEndReason = 'finished' | 'dismissed' | 'no-anchors';

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

  // One atomic post-commit check per stepIndex change: look up the anchor, and either show
  // this step or skip straight past it (e.g. hidden by RBAC) — kept in a single effect so the
  // "does the anchor exist" check and the "advance past it" decision never see different,
  // out-of-sync snapshots of state across separate effects.
  useLayoutEffect(() => {
    const rawStep = stepIndex < tourSteps.length ? tourSteps[stepIndex] : null;
    if (rawStep == null) {
      return;
    }
    if (document.querySelector(rawStep.anchorSelector) != null) {
      shownAnyStep.current = true;
      setCurrentStep(rawStep);
      return;
    }
    setCurrentStep(null);
    if (stepIndex + 1 >= tourSteps.length) {
      onEnd(shownAnyStep.current ? 'finished' : 'no-anchors');
    } else {
      setStepIndex((prev) => prev + 1);
    }
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
