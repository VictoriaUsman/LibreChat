import React, { useCallback, useEffect, useRef } from 'react';
import { useRecoilState, useSetRecoilState } from 'recoil';
import store from '~/store';
import useTourSeen from './useTourSeen';
import useGuidedTour from './useGuidedTour';
import type { TourEndReason } from './useGuidedTour';
import { tourActiveState } from './tourState';
import TourBackdrop from './TourBackdrop';
import TourPopover from './TourPopover';

const GuidedTour = () => {
  const [seen, markSeen] = useTourSeen();
  const [sidebarExpanded, setSidebarExpanded] = useRecoilState(store.sidebarExpanded);
  const setTourActive = useSetRecoilState(tourActiveState);
  const restoreSidebarTo = useRef<boolean | null>(null);

  // Step 3 anchors on `#close-sidebar-button`, and `ExpandedPanel` only assigns that id while
  // the sidebar is expanded — so for anyone whose sidebar is collapsed (the default below
  // 768px, and sticky in localStorage for anyone who has ever collapsed it) the anchor never
  // exists. The step then can't be shown, and its copy describes four rail icons that aren't
  // on screen either. Expand for the duration of the walk and put it back afterwards, so the
  // tour doesn't silently change a preference the user set.
  useEffect(() => {
    if (seen) {
      return;
    }
    setTourActive(true);
    if (restoreSidebarTo.current === null) {
      restoreSidebarTo.current = sidebarExpanded;
    }
    setSidebarExpanded(true);
    // Only on entering the tour: `sidebarExpanded` is deliberately not a dependency, or
    // collapsing the sidebar mid-tour would immediately re-expand it and overwrite the
    // remembered value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seen]);

  const restoreSidebar = useCallback(() => {
    setTourActive(false);
    if (restoreSidebarTo.current !== null) {
      setSidebarExpanded(restoreSidebarTo.current);
      restoreSidebarTo.current = null;
    }
  }, [setSidebarExpanded, setTourActive]);

  // Covers unmount paths that don't go through `handleEnd` (navigating away mid-tour).
  useEffect(() => restoreSidebar, [restoreSidebar]);

  const handleEnd = useCallback(
    (reason: TourEndReason) => {
      if (reason !== 'no-anchors') {
        markSeen(true);
      }
      restoreSidebar();
    },
    [markSeen, restoreSidebar],
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
