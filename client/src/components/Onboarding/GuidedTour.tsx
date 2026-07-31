import React, { useCallback } from 'react';
import useTourSeen from './useTourSeen';
import useGuidedTour from './useGuidedTour';
import type { TourEndReason } from './useGuidedTour';
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

  const { currentStep, stepIndex, totalSteps, isFirstStep, isLastStep, next, back, dismiss } =
    useGuidedTour(handleEnd);

  if (seen) {
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
