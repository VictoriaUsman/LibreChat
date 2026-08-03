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
