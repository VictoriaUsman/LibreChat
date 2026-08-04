import { atom } from 'recoil';

/**
 * True while the guided tour is walking the user through the app.
 *
 * Read by `UnifiedSidebar` so it can suppress its own scrim: below 768px the sidebar renders
 * as an overlay with a `bg-black/50` backdrop of its own, which stacked underneath the tour's
 * backdrop and left the app too dark to see what the popover was pointing at. The tour's
 * backdrop already blocks interaction for the whole screen, so the sidebar's is redundant
 * while the tour is up.
 *
 * Kept in this folder rather than `~/store` on purpose: everything under `Onboarding/` is
 * ours, so it can't conflict when we merge upstream.
 */
export const tourActiveState = atom<boolean>({
  key: 'guidedTourActive',
  default: false,
});
