import { createPortal } from 'react-dom';

/**
 * Rendered by `GuidedTour` for the full lifetime of the walk (not by `TourPopover`, which
 * unmounts/remounts between steps) so it never flickers as the popover moves anchor to anchor.
 *
 * **Barely there, but still blocking.** This was `bg-gray-600/65 dark:bg-black/80`, which defeated
 * the point of the tour: below 768px the sidebar renders its own `bg-black/50` scrim, the two
 * stacked to ~0.83 in light and ~0.90 in dark, and the app underneath was too dark to make out
 * whatever the popover was pointing at. The sidebar's scrim is now suppressed while the tour runs
 * (see `tourState.ts`), and what's left here is the minimum that still reads as modal.
 *
 * **Asymmetric on purpose.** Light mode is fully transparent: the app is bright enough that the
 * popover separates from it unaided. Dark mode keeps `black/35`, because against a near-black app
 * an undimmed backdrop leaves the popover with nothing to lift it off the page. Both values were
 * chosen against the running dev build rather than derived. This matters more than it looks:
 * `ThemeProvider` defaults to `'system'`, so a first-run user on a dark-mode OS meets the tour in
 * dark on their very first load — the dark case is not an edge case.
 *
 * An element with no background still receives pointer events, so interaction stays blocked in
 * light mode too. `pointer-events-none` is what would break that, and its absence is deliberate.
 * Tune the dim here and nowhere else: one backdrop, one place to change it.
 */
const TourBackdrop = () =>
  createPortal(
    <div
      aria-hidden="true"
      data-testid="tour-backdrop"
      className="fixed inset-0 z-[9998] dark:bg-black/35"
    />,
    document.body,
  );

export default TourBackdrop;
