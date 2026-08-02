import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import GuidedTour from '../GuidedTour';
import { ANCHOR_RETRY_INTERVAL_MS, ANCHOR_RETRY_MAX_ATTEMPTS } from '../useGuidedTour';

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
    await waitFor(() => expect(screen.getByText('Artifacts')).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText('Artifacts')).toBeInTheDocument());

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
      expect(screen.queryByText('Artifacts')).not.toBeInTheDocument();
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
      renderTour({ includeToolsAnchor: false });

      expect(screen.getByText('Upload documents')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Next'));

      // Step 2's anchor isn't in the DOM yet — advance through a couple of retries, still
      // short of the full window, then mount it (as a slow-rendering real page would).
      await act(async () => {
        jest.advanceTimersByTime(ANCHOR_RETRY_INTERVAL_MS * 3);
      });
      expect(screen.queryByText('Artifacts')).not.toBeInTheDocument();
      expect(screen.queryByText('Your sidebar')).not.toBeInTheDocument();

      const toolsButton = document.createElement('button');
      toolsButton.id = 'tools-dropdown-button';
      toolsButton.textContent = 'tools';
      document.body.appendChild(toolsButton);

      await act(async () => {
        jest.advanceTimersByTime(ANCHOR_RETRY_INTERVAL_MS);
      });

      expect(screen.getByText('Artifacts')).toBeInTheDocument();
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
    expect(screen.queryByText('Your conversations')).not.toBeInTheDocument();

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

  it('shows a dimmed backdrop while the tour is open', async () => {
    renderTour();
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    expect(screen.getByTestId('tour-backdrop')).toBeInTheDocument();
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

    await waitFor(() => expect(screen.getByText('Tools & Artifacts')).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText('Tools & Artifacts')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Your conversations')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Settings & files')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Done'));

    await waitFor(() => expect(screen.queryByText('Settings & files')).not.toBeInTheDocument());
    expect(screen.queryByTestId('tour-backdrop')).not.toBeInTheDocument();
  });
});
