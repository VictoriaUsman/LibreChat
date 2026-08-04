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

  // Cleanup matters: without it, unmounting while the tour is live (logout, a route change, or
  // Root.tsx's config/terms gate flipping) strands `tourActiveState` at true for the life of the
  // RecoilRoot — which lives above the router, so it survives logout. UnifiedSidebar would then
  // permanently render its scrim as `pointer-events-none opacity-0`, killing tap-outside-to-close
  // on mobile with no dim and no way back.
  useEffect(() => {
    setTourActive(active);
    return () => setTourActive(false);
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

  // Keyed off the step being *looked for*, not the one on screen. `currentStep` is only assigned
  // once its anchor resolves, so keying off it was circular: on desktop with a collapsed sidebar
  // the anchor can't exist until we expand, and we wouldn't expand until the anchor existed — the
  // step just timed out and was skipped, which is precisely the case this fix is for.
  //
  // Still scoped to this one step rather than the whole walk: below 768px the sidebar is a fixed
  // overlay up to 380px wide (`UnifiedSidebar.tsx`), so holding it open covers the composer that
  // steps 1 and 2 anchor to.
  const pendingStep = stepIndex < tourSteps.length ? tourSteps[stepIndex] : null;
  const needsSidebar = active && pendingStep?.id === SIDEBAR_STEP_ID;

  useEffect(() => {
    if (!needsSidebar) {
      return undefined;
    }
    // Read before writing: the setter below persists, so reading afterwards would depend on
    // Recoil's atom-effect ordering to still see the old value.
    const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (restoreSidebarTo.current === null) {
      // Prefer the stored value over the live atom. If this component remounts mid-tour — which
      // Root.tsx can do as config/terms queries resolve — the atom already reads `true` because
      // we set it, and capturing that would make the expansion permanent.
      restoreSidebarTo.current = stored === null ? sidebarExpanded : stored === 'true';
    }
    setSidebarExpanded(true);

    // `sidebarExpanded` is an `atomWithLocalStorage`, so the line above has already written
    // `true` to the user's stored preference, and React cleanup can't undo that on a reload or
    // tab close — anyone quitting mid-tour would keep a permanently expanded sidebar. Put the
    // stored value back and let the in-memory atom carry the expansion for the rest of the step.
    // Deferred a tick because Recoil's `onSet` effect writes after the set is committed.
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
