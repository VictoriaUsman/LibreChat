import { createPortal } from 'react-dom';

/**
 * Rendered by `GuidedTour` for the full lifetime of the walk (not by `TourPopover`, which
 * unmounts/remounts between steps) so it never flickers as the popover moves anchor to anchor.
 *
 * **Invisible, but still blocking.** This was `bg-gray-600/65 dark:bg-black/80`, which defeated
 * the point of the tour: below 768px the sidebar renders its own `bg-black/50` scrim, the two
 * stacked, and the app underneath was too dark to make out whatever the popover was pointing
 * at. The sidebar's scrim is now suppressed while the tour runs (see `tourState.ts`) and this
 * one is transparent — the popover, its arrow, and the fact that nothing else responds are what
 * mark the tour as modal.
 *
 * An element with no background still receives pointer events, so interaction stays blocked.
 * `pointer-events-none` is what would break that, and its absence here is deliberate. To bring
 * a dim back, add a background on this element and nowhere else: one backdrop, one place to
 * tune it. `bg-black/20` is about as far as it can go before legibility suffers again.
 */
const TourBackdrop = () =>
  createPortal(
    <div aria-hidden="true" data-testid="tour-backdrop" className="fixed inset-0 z-[9998]" />,
    document.body,
  );

export default TourBackdrop;
