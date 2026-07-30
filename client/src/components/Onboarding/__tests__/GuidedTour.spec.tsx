import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import GuidedTour from '../GuidedTour';

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
      <button data-testid="new-chat-button">new chat</button>
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
    await waitFor(() => expect(screen.getByText('Tools & Artifacts')).toBeInTheDocument());
    expect(screen.getByText('Step 2 of 4')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(screen.getByText('Your conversations')).toBeInTheDocument());

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
    await waitFor(() => expect(screen.getByText('Tools & Artifacts')).toBeInTheDocument());

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
    renderTour({ includeToolsAnchor: false });
    await waitFor(() => expect(screen.getByText('Upload documents')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Next'));

    // Step 2's anchor (#tools-dropdown-button) doesn't exist, so it's skipped straight to step 3.
    await waitFor(() => expect(screen.getByText('Your conversations')).toBeInTheDocument());
    expect(screen.queryByText('Tools & Artifacts')).not.toBeInTheDocument();
  });
});
