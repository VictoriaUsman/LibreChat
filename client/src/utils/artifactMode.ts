import { ArtifactModes } from 'librechat-data-provider';

/**
 * Fold a persisted artifacts toggle value back to a mode the UI can still reach.
 *
 * The `shadcnui` and `custom` sub-options were removed from the Artifacts control
 * (see PATCHES.md, ADO WI # 12631), but a user who picked one before the removal still
 * has it in localStorage. Restoring it verbatim leaves the badge reading "on" while
 * nothing renders — `useToolToggle` treats any non-empty string as enabled, and the
 * server's `generateArtifactsPrompt` returns null for `CUSTOM`, so no artifact
 * instructions are ever appended. The sub-menu that could clear the stale value is
 * gone, so it only self-heals if the user happens to toggle off and back on.
 *
 * Both stale values fold to `DEFAULT` so the toggle means what it says. Everything
 * else passes through untouched: `''` (off) and the boolean shape used by the other
 * tool toggles must keep their meaning.
 */
export const normalizeArtifactsMode = (value: boolean | string): boolean | string => {
  if (value === ArtifactModes.SHADCNUI || value === ArtifactModes.CUSTOM) {
    return ArtifactModes.DEFAULT;
  }
  return value;
};
