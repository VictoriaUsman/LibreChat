import { createPortal } from 'react-dom';

/**
 * Rendered by `GuidedTour` for the full lifetime of the walk (not by `TourPopover`,
 * which unmounts/remounts between steps) so the dim never flickers as the popover
 * moves from anchor to anchor.
 */
const TourBackdrop = () =>
  createPortal(
    <div
      aria-hidden="true"
      data-testid="tour-backdrop"
      className="fixed inset-0 z-[9998] bg-gray-600/65 dark:bg-black/80"
    />,
    document.body,
  );

export default TourBackdrop;
