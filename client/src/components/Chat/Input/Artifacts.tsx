import { memo, useCallback, useMemo } from 'react';
import { CheckboxButton } from '@librechat/client';
import { ArtifactModes } from 'librechat-data-provider';
import { WandSparkles } from 'lucide-react';
import { useBadgeRowContext } from '~/Providers';
import { useLocalize } from '~/hooks';

interface ArtifactsToggleState {
  enabled: boolean;
  mode: string;
}

function Artifacts() {
  const localize = useLocalize();
  const context = useBadgeRowContext();
  const { toggleState, debouncedChange, isPinned } = context?.artifacts ?? {};

  const currentState = useMemo<ArtifactsToggleState>(() => {
    if (typeof toggleState === 'string' && toggleState) {
      return { enabled: true, mode: toggleState };
    }
    return { enabled: false, mode: '' };
  }, [toggleState]);

  const isEnabled = currentState.enabled;

  const handleToggle = useCallback(() => {
    if (!debouncedChange) return;
    if (isEnabled) {
      debouncedChange({ value: '' });
    } else {
      debouncedChange({ value: ArtifactModes.DEFAULT });
    }
  }, [isEnabled, debouncedChange]);

  if (!isEnabled && !isPinned) {
    return null;
  }

  return (
    <div className="flex">
      <CheckboxButton
        className="max-w-fit"
        checked={isEnabled}
        setValue={handleToggle}
        label={localize('com_ui_artifacts')}
        isCheckedClassName="border-amber-600/40 bg-amber-500/10 hover:bg-amber-700/10"
        icon={<WandSparkles className="icon-md" aria-hidden="true" />}
      />
    </div>
  );
}

export default memo(Artifacts);
