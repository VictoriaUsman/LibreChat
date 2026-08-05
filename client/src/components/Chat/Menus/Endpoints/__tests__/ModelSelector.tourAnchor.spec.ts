import fs from 'fs';
import path from 'path';

/**
 * Merge guard for the guided tour's model-step anchor.
 *
 * `ModelSelector.tsx` is an upstream-owned file carrying one ROMChat addition:
 * `id="model-selector-button"`, which `Onboarding/tourSteps.ts` resolves with
 * `document.querySelector`. Nothing else in the suite would notice if an upstream merge dropped
 * it — `GuidedTour.spec.tsx` mounts its own stand-in anchor, so the tour tests stay green while
 * the real app silently loses the step.
 *
 * The cost of that silence is the reason this exists. A missing anchor is not a visible failure:
 * mid-tour the step burns 12 × 250ms of full-screen, click-blocking, light-mode-invisible
 * backdrop with no popover on it, on every load, for every user, then moves on. No error, no
 * telemetry, nothing to notice until somebody complains.
 *
 * This asserts on source text rather than rendering, deliberately: rendering `ModelSelector`
 * needs the endpoints/query/Recoil provider stack, and a heavyweight render test would be a
 * worse guard than a two-line grep for the exact thing an upstream merge deletes.
 */
describe('ModelSelector — guided tour anchor', () => {
  const source = fs.readFileSync(
    path.join(__dirname, '..', 'ModelSelector.tsx'),
    'utf8',
  );

  it('keeps the tour anchor id on the trigger', () => {
    expect(source).toContain('id="model-selector-button"');
  });

  it('sets it on both the TooltipAnchor and its render element, as upstream does', () => {
    // Upstream sets these ids at both levels for the other two tour anchors
    // (AttachFileMenu.tsx, ToolsDropdown.tsx). Matching that avoids depending on Ariakit's
    // prop-merge order surviving an upgrade.
    const occurrences = source.match(/id="model-selector-button"/g) ?? [];
    expect(occurrences).toHaveLength(2);
  });
});
