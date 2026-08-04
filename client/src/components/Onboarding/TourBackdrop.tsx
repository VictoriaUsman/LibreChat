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
 * **Asymmetric on purpose, and this way round deliberately.** Light mode keeps `black/35`; dark
 * mode is fully transparent. Both values were judged against the running dev build rather than
 * derived, and the pairing was reversed on 2026-08-05 after the first version shipped with the dim
 * on the dark side — dimming an already-near-black app just muddies it, while a bright app needs
 * something to separate the popover from the page behind it.
 *
 * This matters more than it looks: `ThemeProvider` defaults to `'system'`, so a first-run user on
 * a dark-mode OS meets the tour in dark on their very first load. Neither theme is an edge case;
 * both are somebody's first impression.
 *
 * An element with no background still receives pointer events, so interaction stays blocked in
 * dark mode too. `pointer-events-none` is what would break that, and its absence is deliberate.
 * Tune the dim here and nowhere else: one backdrop, one place to change it.
 */
const TourBackdrop = () =>
  createPortal(
    <div
      aria-hidden="true"
      data-testid="tour-backdrop"
      className="fixed inset-0 z-[9998] bg-black/35 dark:bg-transparent"
    />,
    document.body,
  );

export default TourBackdrop;
