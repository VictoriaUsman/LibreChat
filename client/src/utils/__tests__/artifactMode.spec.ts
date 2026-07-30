import { ArtifactModes } from 'librechat-data-provider';

import { normalizeArtifactsMode } from '../artifactMode';

describe('normalizeArtifactsMode', () => {
  it('folds a stale custom value to default so the badge stops lying about being on', () => {
    expect(normalizeArtifactsMode(ArtifactModes.CUSTOM)).toBe(ArtifactModes.DEFAULT);
  });

  it('folds a stale shadcnui value to default', () => {
    expect(normalizeArtifactsMode(ArtifactModes.SHADCNUI)).toBe(ArtifactModes.DEFAULT);
  });

  it('leaves default alone', () => {
    expect(normalizeArtifactsMode(ArtifactModes.DEFAULT)).toBe(ArtifactModes.DEFAULT);
  });

  it('leaves the off value alone rather than turning artifacts on', () => {
    expect(normalizeArtifactsMode('')).toBe('');
  });

  it('passes booleans through untouched for the shared tool-toggle shape', () => {
    expect(normalizeArtifactsMode(false)).toBe(false);
    expect(normalizeArtifactsMode(true)).toBe(true);
  });
});
