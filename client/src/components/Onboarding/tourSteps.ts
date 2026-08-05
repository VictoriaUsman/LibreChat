import type { TranslationKeys } from '~/hooks/useLocalize';

export interface TourStep {
  id: string;
  anchorSelector: string;
  titleKey: TranslationKeys;
  bodyKey: TranslationKeys;
  placement: 'top' | 'bottom' | 'left' | 'right';
}

export const tourSteps: TourStep[] = [
  {
    id: 'upload',
    anchorSelector: '#attach-file-menu-button',
    titleKey: 'com_onboarding_tour_step_upload_title',
    bodyKey: 'com_onboarding_tour_step_upload_body',
    placement: 'top',
  },
  {
    id: 'tools',
    anchorSelector: '#tools-dropdown-button',
    titleKey: 'com_onboarding_tour_step_tools_title',
    bodyKey: 'com_onboarding_tour_step_tools_body',
    placement: 'top',
  },
  {
    // Placed after the composer steps and before the sidebar, so the tour finishes with the chat
    // area before moving to the left rail. Anchored on the model spec selector's trigger: with
    // `modelSpecs.enforce: true` and `interface.modelSelect: false` in `librechat.yaml`, that
    // button is the only model control a user has, and it offers exactly ROMChat Standard and
    // ROMChat Fast.
    //
    // ⚠️ Ordering coupling with the step below. `Header.tsx` renders the model selector only when
    // `!(navVisible && isSmallScreen)`, and the sidebar step force-expands the sidebar on small
    // screens — so this anchor is *unmounted* while that step is showing. Pressing Back from the
    // sidebar step on a phone therefore costs one ~250ms retry (blank popover, backdrop still up)
    // before the sidebar restores and the anchor returns. Self-healing, but if you move this step
    // to sit after the sidebar step, that becomes the forward path and every phone user pays it.
    id: 'model',
    anchorSelector: '#model-selector-button',
    titleKey: 'com_onboarding_tour_step_model_title',
    bodyKey: 'com_onboarding_tour_step_model_body',
    // `bottom`, not `right` like the two steps below it. Those anchor in the left rail, where
    // there is a whole page to their right. This one is in the header (`Header.tsx`, `absolute
    // top-0 h-[52px]`, left-aligned), so "right" means "into the remaining header width". The
    // trigger is `w-full max-w-[70vw]` inside a `max-w-md` wrapper, so on a 390px phone it spans
    // roughly x≈56-330 — leaving ~60px against the popover's 300px plus 19px of offset
    // (sideOffset 10 + a 9px arrow). Radix would not rescue it: `flip` only tries the opposite side,
    // where there is even less room, and its `shift` is configured `crossAxis: false`, so for a
    // `right` placement there is no horizontal correction at all. The Back/Next buttons would
    // hang off the screen edge. For `bottom`, shift's main axis IS horizontal, so Radix clamps
    // the popover into the viewport and the arrow keeps tracking the button.
    placement: 'bottom',
  },
  {
    id: 'sidebar',
    anchorSelector: '#close-sidebar-button',
    titleKey: 'com_onboarding_tour_step_sidebar_title',
    bodyKey: 'com_onboarding_tour_step_sidebar_body',
    placement: 'right',
  },
  {
    id: 'account',
    anchorSelector: '[data-testid="nav-user"]',
    titleKey: 'com_onboarding_tour_step_account_title',
    bodyKey: 'com_onboarding_tour_step_account_body',
    placement: 'right',
  },
];
