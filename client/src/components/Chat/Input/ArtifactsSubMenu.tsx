import React from 'react';
import * as Ariakit from '@ariakit/react';
import { PinIcon } from '@librechat/client';
import { WandSparkles } from 'lucide-react';
import { useLocalize } from '~/hooks';
import { cn } from '~/utils';

interface ArtifactsSubMenuProps {
  isArtifactsPinned: boolean;
  setIsArtifactsPinned: (value: boolean) => void;
  artifactsMode: string;
  handleArtifactsToggle: () => void;
}

const ArtifactsSubMenu = React.forwardRef<HTMLDivElement, ArtifactsSubMenuProps>(
  (
    { isArtifactsPinned, setIsArtifactsPinned, artifactsMode, handleArtifactsToggle, ...props },
    ref,
  ) => {
    const localize = useLocalize();

    const isEnabled = artifactsMode !== '' && artifactsMode !== undefined;

    return (
      <div ref={ref}>
        <Ariakit.MenuItem
          {...props}
          hideOnClick={false}
          role="menuitemcheckbox"
          aria-checked={isEnabled}
          onClick={(e: React.MouseEvent<HTMLDivElement>) => {
            e.stopPropagation();
            handleArtifactsToggle();
          }}
          className="flex w-full cursor-pointer items-center justify-between rounded-lg p-2 hover:bg-surface-hover"
        >
          <div className="flex items-center gap-2">
            <WandSparkles className="icon-md" aria-hidden="true" />
            <span>{localize('com_ui_artifacts')}</span>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setIsArtifactsPinned(!isArtifactsPinned);
            }}
            className={cn(
              'rounded p-1 transition-all duration-200',
              'hover:bg-surface-tertiary hover:shadow-sm',
              !isArtifactsPinned && 'text-text-secondary hover:text-text-primary',
            )}
            aria-label={isArtifactsPinned ? 'Unpin' : 'Pin'}
          >
            <div className="h-4 w-4">
              <PinIcon unpin={isArtifactsPinned} />
            </div>
          </button>
        </Ariakit.MenuItem>
      </div>
    );
  },
);

ArtifactsSubMenu.displayName = 'ArtifactsSubMenu';

export default React.memo(ArtifactsSubMenu);
