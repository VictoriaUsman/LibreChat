import React, { useCallback } from 'react';
import useTourSeen from './useTourSeen';
import useGuidedTour from './useGuidedTour';
import type { TourEndReason } from './useGuidedTour';
import TourBackdrop from './TourBackdrop';
import TourPopover from './TourPopover';

const GuidedTour = () => {
  const [seen, markSeen] = useTourSeen();

  const handleEnd = useCallback(
    (reason: TourEndReason) => {
      if (reason !== 'no-anchors') {
        markSeen(true);
      }
    },
    [markSeen],
  );

  // Deliberately no start gate here. `useGuidedTour` retries each step's anchor lookup
  // (ANCHOR_RETRY_INTERVAL_MS x ANCHOR_RETRY_MAX_ATTEMPTS) instead of checking once, so a
  // late-mounting composer can no longer cause a step to be skipped. That supersedes the
  // earlier `ready`/`enabled` gate, which waited only for step 1's anchor and left every
  // later step exposed to the same race.
  const { currentStep, stepIndex, totalSteps, isFirstStep, isLastStep, next, back, dismiss } =
    useGuidedTour(handleEnd);

  if (seen) {
    return null;
  }

  return (
    <>
      {/* Mounted here, not inside TourPopover, so it stays up (no dim flicker) across the
          brief frames where currentStep is null while skipping a missing anchor. */}
      <TourBackdrop />
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
    </>
  );
};

export default React.memo(GuidedTour);
