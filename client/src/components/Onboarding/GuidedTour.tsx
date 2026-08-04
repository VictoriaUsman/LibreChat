import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRecoilState, useSetRecoilState } from 'recoil';
import store from '~/store';
import useTourSeen from './useTourSeen';
import useGuidedTour from './useGuidedTour';
import type { TourEndReason } from './useGuidedTour';
import { tourSteps } from './tourSteps';
import { tourActiveState } from './tourState';
import TourBackdrop from './TourBackdrop';
import TourPopover from './TourPopover';

/** The one step that needs the sidebar open. Matched by id, not index, so reordering steps
 *  can't silently point this at the wrong one. */
const SIDEBAR_STEP_ID = 'sidebar';
/** Key `store.sidebarExpanded` persists under (see `atomWithLocalStorage`). */
const SIDEBAR_STORAGE_KEY = 'unifiedSidebarExpanded';

const GuidedTour = () => {
  const [seen, markSeen] = useTourSeen();
  const [sidebarExpanded, setSidebarExpanded] = useRecoilState(store.sidebarExpanded);
  const setTourActive = useSetRecoilState(tourActiveState);
  const [ended, setEnded] = useState(false);
  const restoreSidebarTo = useRef<boolean | null>(null);

  const active = !seen && !ended;

  useEffect(() => {
    setTourActive(active);
  }, [active, setTourActive]);

  const { currentStep, stepIndex, totalSteps, isFirstStep, isLastStep, next, back, dismiss } =
    useGuidedTour(
      // Deliberately no start gate. `useGuidedTour` retries each step's anchor lookup instead of
      // checking once, so a late-mounting composer can no longer cause a step to be skipped.
      useCallback(
        (reason: TourEndReason) => {
          if (reason !== 'no-anchors') {
            markSeen(true);
          }
          // Even on 'no-anchors' the tour is over. Without this the component keeps rendering —
          // and since the backdrop is now transparent in light mode, that left an invisible
          // full-screen click-blocker over a normal-looking app until the next reload.
          setEnded(true);
        },
        [markSeen],
      ),
    );

  // Only the sidebar step needs the sidebar open, and expanding for the whole walk actively
  // breaks the earlier steps: below 768px the sidebar is a fixed overlay up to 380px wide
  // (`UnifiedSidebar.tsx`), so holding it open covers the composer that steps 1 and 2 point at.
  const needsSidebar = active && currentStep?.id === SIDEBAR_STEP_ID;

  useEffect(() => {
    if (!needsSidebar) {
      return;
    }
    if (restoreSidebarTo.current === null) {
      restoreSidebarTo.current = sidebarExpanded;
    }
    setSidebarExpanded(true);

    // `sidebarExpanded` is an `atomWithLocalStorage`, so the line above has already written
    // `true` to the user's stored preference. React cleanup can't undo that on a reload or a
    // tab close, which would leave anyone who quit mid-tour with a permanently expanded
    // sidebar. Put the stored value back immediately and let the in-memory atom carry the
    // expansion for the rest of the step. Deferred a tick because recoil's `onSet` effect
    // writes after the set is committed, and this has to land last.
    const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    const timeoutId = setTimeout(() => {
      if (stored === null) {
        localStorage.removeItem(SIDEBAR_STORAGE_KEY);
      } else {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, stored);
      }
    }, 0);
    return () => clearTimeout(timeoutId);
    // Entering the step only — `sidebarExpanded` is not a dependency, or a collapse during the
    // step would immediately re-expand and overwrite the remembered value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsSidebar]);

  const restoreSidebar = useCallback(() => {
    if (restoreSidebarTo.current !== null) {
      setSidebarExpanded(restoreSidebarTo.current);
      restoreSidebarTo.current = null;
    }
  }, [setSidebarExpanded]);

  // Leaving the sidebar step — forwards, backwards, or by ending the tour — and any unmount.
  useEffect(() => {
    if (needsSidebar) {
      return restoreSidebar;
    }
    restoreSidebar();
    return undefined;
  }, [needsSidebar, restoreSidebar]);

  if (!active) {
    return null;
  }

  return (
    <>
      {/* Mounted here, not inside TourPopover, so it stays put across the frames where
          currentStep is null while an anchor is still being looked for. */}
      <TourBackdrop />
      <TourPopover
        step={currentStep}
        // Derived from the step actually on screen, not from `stepIndex`. `stepIndex` advances
        // on click and paints before the anchor lookup runs, so feeding it straight through
        // rendered one frame of the outgoing step's content under the incoming step's number —
        // a single-frame flash of the exact bug this branch exists to fix.
        stepIndex={currentStep ? tourSteps.indexOf(currentStep) : stepIndex}
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
