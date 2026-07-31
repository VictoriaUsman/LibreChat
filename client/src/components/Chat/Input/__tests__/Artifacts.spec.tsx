import React from 'react';
import userEvent from '@testing-library/user-event';
import { ArtifactModes } from 'librechat-data-provider';
import { render, screen } from '@testing-library/react';
import Artifacts from '../Artifacts';

const mockArtifacts = {
  toggleState: '' as string | boolean,
  debouncedChange: jest.fn(),
  isPinned: true,
};

jest.mock('~/Providers', () => ({
  useBadgeRowContext: () => ({ artifacts: mockArtifacts }),
}));

jest.mock('~/hooks', () => ({
  useLocalize: () => (key: string) => key,
}));

describe('Artifacts badge', () => {
  beforeEach(() => {
    mockArtifacts.debouncedChange.mockClear();
    mockArtifacts.toggleState = '';
    mockArtifacts.isPinned = true;
  });

  it('is off by default for a fresh user and stays hidden when unpinned', () => {
    mockArtifacts.isPinned = false;
    const { container } = render(<Artifacts />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a single unchecked toggle when pinned and not yet enabled', () => {
    render(<Artifacts />);
    expect(screen.getAllByRole('checkbox')).toHaveLength(1);
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it.each([
    ['off', ''],
    ['on', ArtifactModes.DEFAULT],
  ])('exposes no sub-options while %s', (_label, mode) => {
    mockArtifacts.toggleState = mode;
    render(<Artifacts />);

    const toggle = screen.getByRole('checkbox');
    expect(toggle).toHaveAttribute('aria-checked', String(mode !== ''));
    expect(screen.queryByText('com_ui_include_shadcnui')).not.toBeInTheDocument();
    expect(screen.queryByText('com_ui_custom_prompt_mode')).not.toBeInTheDocument();
    expect(screen.queryByText('com_ui_artifacts_options')).not.toBeInTheDocument();
    expect(screen.queryAllByRole('menuitem')).toHaveLength(0);
    expect(screen.getAllByRole('checkbox')).toHaveLength(1);
  });

  it('turns artifacts on via the keyboard', async () => {
    const user = userEvent.setup();
    render(<Artifacts />);

    await user.tab();
    expect(screen.getByRole('checkbox')).toHaveFocus();
    await user.keyboard(' ');

    expect(mockArtifacts.debouncedChange).toHaveBeenCalledWith({ value: ArtifactModes.DEFAULT });
  });

  it('turns artifacts off without selecting a mode', async () => {
    mockArtifacts.toggleState = ArtifactModes.DEFAULT;
    const user = userEvent.setup();
    render(<Artifacts />);

    await user.click(screen.getByRole('checkbox'));

    expect(mockArtifacts.debouncedChange).toHaveBeenCalledWith({ value: '' });
  });
});
