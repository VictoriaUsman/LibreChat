import React, { useRef, useLayoutEffect, useEffect } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { motion, AnimatePresence } from 'framer-motion';
import { useLocalize } from '~/hooks';
import { cn } from '~/utils';
import type { TourStep } from './tourSteps';

interface TourPopoverProps {
  step: TourStep | null;
  stepIndex: number;
  totalSteps: number;
  isFirstStep: boolean;
  isLastStep: boolean;
  onNext: () => void;
  onBack: () => void;
  onDismiss: () => void;
}

const stepVariants = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1, transition: { duration: 0.3, ease: 'easeOut' } },
  // Instant, not faded: Popper repositions to the next step's anchor the moment `step`
  // changes, so an animated (visible) exit would show the outgoing content sliding/fading
  // at the OLD position and then jumping mid-fade to the NEW one — the "flash" on Next.
  // Removing it outright avoids the reposition-while-visible window entirely; only the
  // incoming step still animates in, at the correct (already-updated) position.
  exit: { opacity: 0, transition: { duration: 0 } },
};

const TourPopover = ({
  step,
  stepIndex,
  totalSteps,
  isFirstStep,
  isLastStep,
  onNext,
  onBack,
  onDismiss,
}: TourPopoverProps) => {
  const localize = useLocalize();
  const anchorRef = useRef<HTMLElement | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const primaryButtonRef = useRef<HTMLButtonElement>(null);

  // Render exactly the step we were given, or nothing.
  //
  // This used to fall back to the last rendered step whenever `step` was null, to spare Radix
  // an unmount/remount between steps. That fallback was actively harmful: `step` is null for
  // the entire time `useGuidedTour` is hunting for an anchor that hasn't appeared, so the
  // fallback rendered the PREVIOUS step's content, pinned to the PREVIOUS step's anchor, under
  // the incoming step's number. Showing nothing for a moment is recoverable; confidently
  // showing the wrong step is not. The backdrop is mounted by `GuidedTour`, so it stays put
  // regardless and there is no dim flicker either way.
  const displayStep = step;

  // Runs as a layout effect (before Radix Popper's own effect) so the anchor is already
  // up to date by the time Popper reads it for positioning.
  useLayoutEffect(() => {
    anchorRef.current = displayStep
      ? document.querySelector<HTMLElement>(displayStep.anchorSelector)
      : null;
  }, [displayStep]);

  useEffect(() => {
    if (displayStep) {
      primaryButtonRef.current?.focus();
    }
  }, [displayStep]);

  useEffect(() => {
    if (!displayStep) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onDismiss();
        return;
      }
      if (e.key !== 'Tab' || !contentRef.current) {
        return;
      }
      const focusable = contentRef.current.querySelectorAll<HTMLElement>('button:not([disabled])');
      if (focusable.length === 0) {
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, [displayStep, onDismiss]);

  if (!displayStep) {
    return null;
  }

  return (
    <Popover.Root open>
      <Popover.Anchor virtualRef={anchorRef} />
      <Popover.Portal>
        <Popover.Content
          side={displayStep.placement}
          sideOffset={10}
          align="center"
          aria-modal="true"
          onOpenAutoFocus={(e) => e.preventDefault()}
          onCloseAutoFocus={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
          className="z-[9999]"
        >
          {/* Radix repositions and re-rotates this to keep pointing at the anchor on every
              side/align it picks (including collision-driven flips at narrow widths), so it
              doesn't need to be re-derived from `step.placement` by hand. */}
          <Popover.Arrow
            width={18}
            height={9}
            className="fill-surface-primary stroke-border-medium"
            strokeWidth={1}
          />
          <AnimatePresence mode="wait">
            <motion.div
              key={displayStep.id}
              ref={contentRef}
              role="dialog"
              aria-modal="true"
              aria-label={localize('com_onboarding_tour_label')}
              variants={stepVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className={cn(
                'w-[300px] rounded-xl border border-border-medium',
                'bg-surface-primary p-4 shadow-lg',
              )}
            >
              <p className="mb-1 text-xs font-medium text-text-secondary">
                {localize('com_onboarding_tour_step_of', { 0: stepIndex + 1, 1: totalSteps })}
              </p>
              <h2 className="mb-1.5 text-base font-semibold text-text-primary">
                {localize(displayStep.titleKey)}
              </h2>
              <p className="mb-4 text-sm text-text-secondary">{localize(displayStep.bodyKey)}</p>
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={onDismiss}
                  className="text-sm text-text-secondary hover:text-text-primary"
                >
                  {localize('com_onboarding_tour_skip')}
                </button>
                <div className="flex items-center gap-2">
                  {!isFirstStep && (
                    <button
                      type="button"
                      onClick={onBack}
                      className="rounded-lg border border-border-medium px-3 py-1.5 text-sm text-text-primary hover:bg-surface-hover"
                    >
                      {localize('com_onboarding_tour_back')}
                    </button>
                  )}
                  <button
                    type="button"
                    ref={primaryButtonRef}
                    onClick={onNext}
                    className="rounded-lg bg-surface-submit px-3 py-1.5 text-sm text-primary-foreground hover:bg-surface-submit-hover"
                  >
                    {isLastStep
                      ? localize('com_onboarding_tour_finish')
                      : localize('com_onboarding_tour_next')}
                  </button>
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
};

export default TourPopover;
