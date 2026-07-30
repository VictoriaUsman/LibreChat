import React, { useState, useEffect, useCallback } from 'react';
import useTourSeen from './useTourSeen';
import useGuidedTour from './useGuidedTour';
import type { TourEndReason } from './useGuidedTour';
import TourPopover from './TourPopover';

const GuidedTour = () => {
  const [seen, markSeen] = useTourSeen();
  const [ready, setReady] = useState(false);

  // Wait two frames after mount so the app shell (sidebar, composer, nav) has actually
  // painted before looking up anchor elements — Root.tsx has no existing "shell painted"
  // signal to hook into.
  useEffect(() => {
    if (seen) {
      return;
    }
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => setReady(true));
    });
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
    };
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
