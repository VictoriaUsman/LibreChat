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
    id: 'model',
    anchorSelector: '#model-selector-button',
    titleKey: 'com_onboarding_tour_step_model_title',
    bodyKey: 'com_onboarding_tour_step_model_body',
    placement: 'right',
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
