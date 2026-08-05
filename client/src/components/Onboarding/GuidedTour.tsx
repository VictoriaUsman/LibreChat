import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRecoilState, useSetRecoilState } from 'recoil';
import { useMediaQuery } from '@librechat/client';
import store from '~/store';
import useTourSeen from './useTourSeen';
import useGuidedTour from './useGuidedTour';
import type { TourEndReason } from './useGuidedTour';
import { tourSteps } from './tourSteps';
import { tourActiveState } from './tourState';
import TourBackdrop from './TourBackdrop';
import TourPopover from './TourPopover';

/** Steps whose anchor lives in the sidebar. Matched by id, not index, so reordering steps can't
 *  silently point this at the wrong one.
 *
 *  `account` is only here below 768px. `AccountSettings` (the `[data-testid="nav-user"]` anchor)
 *  renders inside `ExpandedPanel`, which on desktop stays on screen as a narrow rail when
 *  collapsed — but on mobile the whole panel is translated off-screen and marked `inert`. Since
 *  `document.querySelector` doesn't care about transforms the anchor still *resolves*, so there's
 *  no retry and no skip: the popover would simply point at something sliding out of view. */
const SIDEBAR_STEP_IDS = ['sidebar'];
const SIDEBAR_STEP_IDS_SMALL_SCREEN = ['sidebar', 'account'];
/** Key `store.sidebarExpanded` persists under (see `atomWithLocalStorage`). */
const SIDEBAR_STORAGE_KEY = 'unifiedSidebarExpanded';

const GuidedTour = () => {
  const [seen, markSeen] = useTourSeen();
  const [sidebarExpanded, setSidebarExpanded] = useRecoilState(store.sidebarExpanded);
  const setTourActive = useSetRecoilState(tourActiveState);
  const [ended, setEnded] = useState(false);
  const isSmallScreen = useMediaQuery('(max-width: 768px)');
  const restoreSidebarTo = useRef<boolean | null>(null);
  /** True when the user had no stored sidebar preference before the tour, so restoring must
   *  clear the key again rather than persisting a value the tour invented. The default is
   *  breakpoint-dependent, so pinning it would stop it following a resize across 768px. */
  const hadNoStoredPreference = useRef(false);

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

  // `isFirstStep`/`isLastStep` are deliberately not taken from the hook — they're derived below
  // from the step on screen, for the reason spelled out at the TourPopover props.
  const { currentStep, stepIndex, totalSteps, next, back, dismiss } = useGuidedTour(
      // Deliberately no start gate. `useGuidedTour` retries each step's anchor lookup instead of
      // checking once, so a late-mounting composer can no longer cause a step to be skipped.
      useCallback(
        (reason: TourEndReason) => {
          if (reason !== 'no-anchors') {
            markSeen(true);
          }
          // Even on 'no-anchors' the tour is over. Without this the component keeps rendering —
          // and since the backdrop is transparent in dark mode, that left an invisible
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
  const sidebarStepIds = isSmallScreen ? SIDEBAR_STEP_IDS_SMALL_SCREEN : SIDEBAR_STEP_IDS;
  const needsSidebar = active && pendingStep != null && sidebarStepIds.includes(pendingStep.id);

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
      hadNoStoredPreference.current = stored === null;
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
    if (restoreSidebarTo.current === null) {
      return;
    }
    setSidebarExpanded(restoreSidebarTo.current);
    restoreSidebarTo.current = null;
    if (hadNoStoredPreference.current) {
      // The setter above persists, so a user who had never set this would end the tour with a
      // pinned value. Clear it again on the next tick (after Recoil's `onSet` writes) so the
      // breakpoint default keeps applying.
      hadNoStoredPreference.current = false;
      setTimeout(() => localStorage.removeItem(SIDEBAR_STORAGE_KEY), 0);
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

  const displayIndex = currentStep ? tourSteps.indexOf(currentStep) : stepIndex;

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
        // All three derived from the step actually on screen, not from `stepIndex`. `stepIndex`
        // advances on click and paints before the anchor lookup runs, so feeding it straight
        // through rendered one frame of the outgoing step's content under the incoming step's
        // number — and, while the number alone was fixed, the incoming step's *button semantics*:
        // Back appearing on step 1, or the primary button reading "Done" over step 3's copy.
        stepIndex={displayIndex}
        totalSteps={totalSteps}
        isFirstStep={displayIndex === 0}
        isLastStep={displayIndex >= totalSteps - 1}
        onNext={next}
        onBack={back}
        onDismiss={dismiss}
      />
    </>
  );
};

export default React.memo(GuidedTour);
