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
 * mid-tour the step burns 12 × 250ms of full-screen, click-blocking backdrop with no popover on
 * it — invisible in dark mode, where the backdrop is transparent (`TourBackdrop.tsx`) — on every
 * load, for every user, then moves on. No error, no telemetry, nothing to notice until somebody
 * complains.
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
    // Presence is the whole invariant. The id is currently set at two levels — on the
    // `TooltipAnchor` and on its render element — mirroring how upstream writes the other two
    // tour anchors, but either one alone lands the attribute on the same single DOM node, so
    // asserting a count here would fail a legitimate simplification while proving nothing extra.
    expect(source).toContain('id="model-selector-button"');
  });
});
