import React, { useState, useEffect, useCallback } from 'react';
import useTourSeen from './useTourSeen';
import useGuidedTour from './useGuidedTour';
import type { TourEndReason } from './useGuidedTour';
import { tourSteps } from './tourSteps';
import TourPopover from './TourPopover';

/**
 * How long to keep waiting for the first step's anchor before starting anyway.
 * The sidebar shell paints almost immediately, but the composer anchors
 * (`#attach-file-menu-button`, `#tools-dropdown-button`) only mount once the
 * startup-config and endpoints queries resolve, which is network-bound.
 */
const ANCHOR_WAIT_TIMEOUT_MS = 8_000;

const GuidedTour = () => {
  const [seen, markSeen] = useTourSeen();
  const [ready, setReady] = useState(false);

  // Wait for the FIRST step's anchor before starting the walk.
  //
  // A fixed frame count was not enough. The sidebar anchors (steps 3-4) paint on the
  // first frames, but the composer anchors (steps 1-2) mount only after the
  // startup-config and endpoints queries resolve. On a cold load the walk therefore
  // began before the composer existed, skipped the upload step — the whole point of
  // the tour — and a later step still marked the tour seen, so it never came back.
  //
  // Only step 1 is waited on, deliberately: waiting for *every* anchor would stall the
  // tour for the full timeout whenever a step is legitimately absent (e.g. hidden by
  // permissions). Later steps keep the existing skip-if-missing behaviour. The timeout
  // is a backstop so a never-appearing anchor can't block the tour forever.
  useEffect(() => {
    if (seen) {
      return;
    }
    const firstAnchor = tourSteps[0]?.anchorSelector;
    if (firstAnchor == null) {
      setReady(true);
      return;
    }
    let frame = 0;
    const deadline = Date.now() + ANCHOR_WAIT_TIMEOUT_MS;
    const poll = () => {
      if (document.querySelector(firstAnchor) != null || Date.now() >= deadline) {
        setReady(true);
        return;
      }
      frame = requestAnimationFrame(poll);
    };
    frame = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(frame);
  }, [seen]);

  const handleEnd = useCallback(
    (reason: TourEndReason) => {
      if (reason !== 'no-anchors') {
        markSeen(true);
      }
      setReady(false);
    },
    [markSeen],
  );

  const { currentStep, stepIndex, totalSteps, isFirstStep, isLastStep, next, back, dismiss } =
    useGuidedTour(handleEnd);

  if (seen || !ready) {
    return null;
  }

  return (
    <TourPopover
      step={currentStep}
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      isFirstStep={isFirstStep}
      isLastStep={isLastStep}
      onNext={next}
      onBack={back}
      onDismiss={dismiss}
    />
  );
};

export default React.memo(GuidedTour);
