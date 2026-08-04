import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import GuidedTour from '../GuidedTour';
import { ANCHOR_RETRY_INTERVAL_MS, ANCHOR_RETRY_MAX_ATTEMPTS } from '../useGuidedTour';
import { tourSteps } from '../tourSteps';

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function renderTour({ includeToolsAnchor = true }: { includeToolsAnchor?: boolean } = {}) {
  return render(
    <RecoilRoot>
      {/* eslint-disable-next-line i18next/no-literal-string */}
      <button id="attach-file-menu-button">paperclip</button>
      {includeToolsAnchor && (
        // eslint-disable-next-line i18next/no-literal-string
        <button id="tools-dropdown-button">tools</button>
      )}
      {/* eslint-disable-next-line i18next/no-literal-string */}
      <button id="close-sidebar-button">close sidebar</button>
      {/* eslint-disable-next-line i18next/no-literal-string */}
      <button data-testid="nav-user">account</button>
      <GuidedTour />
    </RecoilRoot>,
  );
}

describe('GuidedTour', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('shows the first step on first load when not seen', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
    expect(screen.getByText('Step 1 of 4')).toBeInTheDocument();
  });

  it('does not appear again once already marked seen', async () => {
    localStorage.setItem('guidedTourSeen', JSON.stringify(true));
    renderTour();
    await act(async () => {
      await sleep(100);
    });
    expect(screen.queryByText('Upload documents')).not.toBeInTheDocument();
  });

  it('reappears after localStorage is cleared', async () => {
    localStorage.setItem('guidedTourSeen', JSON.stringify(true));
    const { unmount } = renderTour();
    await act(async () => {
      await sleep(100);
    });
    expect(screen.queryByText('Upload documents')).not.toBeInTheDocument();
    unmount();

    localStorage.clear();
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
  });

  it('dismisses on Escape and marks the tour as seen', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByText('Upload documents')).not.toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem('guidedTourSeen') ?? 'false')).toBe(true);
  });

  it('marks the tour as seen when Skip is clicked', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Skip'));

    await waitFor(() => expect(screen.queryByText('Upload documents')).not.toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem('guidedTourSeen') ?? 'false')).toBe(true);
  });

  it('advances through every step with Next, then Finish marks it seen', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Tools')).toBeInTheDocument());
    expect(screen.getByText('Step 2 of 4')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Your sidebar')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Settings & files')).toBeInTheDocument());
    expect(screen.getByText('Step 4 of 4')).toBeInTheDocument();

    // Last step's primary button reads "Done", not "Next".
    expect(screen.queryByText('Next')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Done'));

    await waitFor(() => expect(screen.queryByText('Settings & files')).not.toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem('guidedTourSeen') ?? 'false')).toBe(true);
  });

  it('goes back to the previous step with Back, and hides Back on the first step', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
    expect(screen.queryByText('Back')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Tools')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Back'));
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
    expect(screen.queryByText('Back')).not.toBeInTheDocument();
  });

  it('traps Tab focus within the popover buttons', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    const skipButton = screen.getByText('Skip');
    const nextButton = screen.getByText('Next');

    nextButton.focus();
    expect(document.activeElement).toBe(nextButton);

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(skipButton);

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(nextButton);
  });

  it('skips a step whose anchor element is missing from the DOM', async () => {
    jest.useFakeTimers();
    try {
      renderTour({ includeToolsAnchor: false });

      // Step 1's anchor already exists, so it resolves on the very first (synchronous) check —
      // no retry/timer advance needed yet.
      expect(screen.getByText('Upload documents')).toBeInTheDocument();

      fireEvent.click(screen.getByText('Next'));

      // Step 2's anchor (#tools-dropdown-button) doesn't exist. Fast-forward through the full
      // retry window so it's confirmed genuinely absent (not just not-yet-rendered) and
      // skipped straight to step 3.
      await act(async () => {
        jest.advanceTimersByTime((ANCHOR_RETRY_MAX_ATTEMPTS + 2) * ANCHOR_RETRY_INTERVAL_MS);
      });

      expect(screen.getByText('Your sidebar')).toBeInTheDocument();
      expect(screen.queryByText('Tools')).not.toBeInTheDocument();
    } finally {
      jest.useRealTimers();
    }
  });

  it('retries a not-yet-rendered anchor instead of skipping it immediately', async () => {
    // Simulates a real page load where the anchor mounts slightly after the tour starts
    // checking for it, rather than being either immediately present or permanently absent.
    // The anchor is added via direct DOM mutation (not rerender()/new JSX): inserting a new
    // sibling ahead of GuidedTour in an unkeyed children array shifts its position, which
    // React's reconciler treats as an unmount+remount of GuidedTour itself — resetting its
    // internal stepIndex state and invalidating the whole test. Mutating the DOM directly
    // matches how the real anchor appears in production (document.querySelector doesn't care
    // how an element got there) without perturbing React's tree at all.
    jest.useFakeTimers();
    try {
      const { container } = renderTour({ includeToolsAnchor: false });

      expect(screen.getByText('Upload documents')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Next'));

      // Step 2's anchor isn't in the DOM yet — advance through a couple of retries, still
      // short of the full window, then mount it (as a slow-rendering real page would).
      await act(async () => {
        jest.advanceTimersByTime(ANCHOR_RETRY_INTERVAL_MS * 3);
      });
      expect(screen.queryByText('Tools')).not.toBeInTheDocument();
      expect(screen.queryByText('Your sidebar')).not.toBeInTheDocument();

      const toolsButton = document.createElement('button');
      toolsButton.id = 'tools-dropdown-button';
      toolsButton.textContent = 'tools';
      // Into RTL's container, not document.body: `cleanup()` only unmounts what it rendered, and
      // nothing here clears document.body, so a stray #tools-dropdown-button leaks into every
      // later test and silently satisfies anchor lookups that were meant to fail. Appending to
      // the container keeps the property this test cares about — a direct DOM mutation that
      // doesn't perturb React's tree — while getting cleaned up.
      container.append(toolsButton);

      await act(async () => {
        jest.advanceTimersByTime(ANCHOR_RETRY_INTERVAL_MS);
      });

      expect(screen.getByText('Tools')).toBeInTheDocument();
    } finally {
      jest.useRealTimers();
    }
  });

  it('waits for a late-mounting anchor instead of skipping past it', async () => {
    // The composer anchors mount only after the startup-config/endpoints queries resolve,
    // so on a cold load they are absent for the first frames. The tour must wait for them
    // rather than skipping the upload step — which is the whole point of the tour.
    const { container } = render(
      <RecoilRoot>
        {/* eslint-disable-next-line i18next/no-literal-string */}
        <button data-testid="new-chat-button">new chat</button>
        {/* eslint-disable-next-line i18next/no-literal-string */}
        <button data-testid="nav-user">account</button>
        <GuidedTour />
      </RecoilRoot>,
    );

    // Sidebar anchors are present, composer anchors are not — the tour must not start yet.
    await act(async () => {
      await sleep(50);
    });
    expect(screen.queryByText('Upload documents')).not.toBeInTheDocument();
    expect(screen.queryByText('Your sidebar')).not.toBeInTheDocument();

    // Composer paints late.
    await act(async () => {
      const paperclip = document.createElement('button');
      paperclip.id = 'attach-file-menu-button';
      const tools = document.createElement('button');
      tools.id = 'tools-dropdown-button';
      container.append(paperclip, tools);
      await sleep(50);
    });

    // Step 1 is now shown rather than having been skipped.
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
    expect(screen.getByText('Step 1 of 4')).toBeInTheDocument();
  });

  it('still starts promptly when a later step’s anchor is absent', async () => {
    // Only step 1's anchor is waited on. A missing later anchor must not stall startup
    // for the full timeout — it is skipped as before.
    renderTour({ includeToolsAnchor: false });
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
    expect(screen.getByText('Step 1 of 4')).toBeInTheDocument();
  });

  it('covers the screen with a click-blocking backdrop while the tour is open', async () => {
    // Deliberately not "dimmed" any more: the backdrop is transparent so the user can see what
    // the popover is pointing at. It still has to be present and still has to receive pointer
    // events — `pointer-events-none` here would silently unblock the whole app.
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    const backdrop = screen.getByTestId('tour-backdrop');
    expect(backdrop).toBeInTheDocument();
    expect(backdrop).not.toHaveClass('pointer-events-none');
    // Dark mode is transparent by design — dimming an already-near-black app just muddies it —
    // while light mode keeps a dim to separate the popover from a bright page. Nothing else in
    // the repo pins these, so dropping either would silently regress one theme with no other
    // signal. Note the pairing was reversed once already; assert both halves, not just one.
    expect(backdrop).toHaveClass('bg-black/35');
    expect(backdrop).toHaveClass('dark:bg-transparent');
  });

  it('shows nothing rather than the previous step while an anchor is pending', async () => {
    // Regression: `currentStep` used to keep pointing at the outgoing step for the whole retry
    // window while `stepIndex` had already advanced, and TourPopover fell back to the last
    // rendered step. Together they rendered step 1's content on step 1's anchor beneath a
    // "Step 2 of 4" footer — reported in dev as step 3 pointing at the chat toggles.
    jest.useFakeTimers();
    try {
      const { container } = renderTour({ includeToolsAnchor: false });

      expect(screen.getByText('Upload documents')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Next'));

      await act(async () => {
        jest.advanceTimersByTime(ANCHOR_RETRY_INTERVAL_MS * 3);
      });

      // Step 2 can't render yet, but step 1 must not still be on screen under step 2's number.
      expect(screen.queryByText('Upload documents')).not.toBeInTheDocument();
      expect(screen.queryByText('Tools')).not.toBeInTheDocument();
      // The footer assertion is belt-and-braces, not independent evidence: with no popover
      // mounted there is no footer of any number. The `tourSteps.indexOf(currentStep)` derivation
      // it guards is unobservable here by construction — that it can't be observed IS the fix.
      expect(screen.queryByText('Step 2 of 4')).not.toBeInTheDocument();

      // And it must still recover once the anchor turns up, inside the mid-tour window.
      const toolsButton = document.createElement('button');
      toolsButton.id = 'tools-dropdown-button';
      toolsButton.textContent = 'tools';
      container.append(toolsButton);

      await act(async () => {
        jest.advanceTimersByTime(ANCHOR_RETRY_INTERVAL_MS);
      });

      expect(screen.getByText('Tools')).toBeInTheDocument();
      expect(screen.getByText('Step 2 of 4')).toBeInTheDocument();
    } finally {
      jest.useRealTimers();
    }
  });

  it('stops blocking the screen when no anchors are found at all', async () => {
    // 'no-anchors' deliberately doesn't mark the tour seen, so it can run again on a healthier
    // load. It must still tear the backdrop down: it is transparent in light mode, so leaving
    // it mounted swallows every click over an app that looks completely normal.
    jest.useFakeTimers();
    try {
      render(
        <RecoilRoot>
          <GuidedTour />
        </RecoilRoot>,
      );

      // One step transition per act() block. Timer callbacks queue state updates that React only
      // flushes when the act scope resolves, so the next step's effect — and the fresh timer it
      // schedules — doesn't exist until after advanceTimersByTime has returned. A single big
      // advance multiplied by the step count would silently stall after the first transition.
      // Looping once per step is more than enough: the whole-tour attempt budget ends the tour
      // before every step gets its own full window, and extra advances after that are harmless.
      for (let i = 0; i < tourSteps.length; i++) {
        await act(async () => {
          jest.advanceTimersByTime((ANCHOR_RETRY_MAX_ATTEMPTS + 2) * ANCHOR_RETRY_INTERVAL_MS);
        });
      }

      expect(screen.queryByTestId('tour-backdrop')).not.toBeInTheDocument();
      // Not marked seen — a later load with a healthy DOM should still get the tour.
      expect(localStorage.getItem('guidedTourSeen')).not.toBe('true');
    } finally {
      jest.useRealTimers();
    }
  });

  it('announces the popover as a modal dialog to assistive technology', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    const dialog = screen.getByRole('dialog', { name: 'Guided tour' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('keeps the backdrop mounted across a step transition', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
    expect(screen.getByTestId('tour-backdrop')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Next'));

    await waitFor(() => expect(screen.getByText('Tools')).toBeInTheDocument());
    expect(screen.getByTestId('tour-backdrop')).toBeInTheDocument();
  });

  it('removes the backdrop completely when dismissed with Escape', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());
    expect(screen.getByTestId('tour-backdrop')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByText('Upload documents')).not.toBeInTheDocument());
    expect(screen.queryByTestId('tour-backdrop')).not.toBeInTheDocument();
  });

  it('removes the backdrop completely when Skip is clicked', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Skip'));

    await waitFor(() => expect(screen.queryByText('Upload documents')).not.toBeInTheDocument());
    expect(screen.queryByTestId('tour-backdrop')).not.toBeInTheDocument();
  });

  it('removes the backdrop completely once the tour is finished', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Tools')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Your sidebar')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Settings & files')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Done'));

    await waitFor(() => expect(screen.queryByText('Settings & files')).not.toBeInTheDocument());
    expect(screen.queryByTestId('tour-backdrop')).not.toBeInTheDocument();
  });
});
