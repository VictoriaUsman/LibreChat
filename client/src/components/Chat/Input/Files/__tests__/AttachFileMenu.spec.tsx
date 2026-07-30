import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { RecoilRoot, useRecoilValue } from 'recoil';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EToolResources } from 'librechat-data-provider';
import { ephemeralAgentByConvoId } from '~/store';
import AttachFileMenu from '../AttachFileMenu';

jest.mock('~/hooks', () => ({
  useAgentToolPermissions: jest.fn(),
  useAgentCapabilities: jest.fn(),
  useGetAgentsConfig: jest.fn(),
  useFileHandlingNoChatContext: jest.fn(),
  useHasAccess: jest.fn(),
  useLocalize: jest.fn(),
}));

jest.mock('@librechat/client', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require('react');
  return {
    FileUpload: R.forwardRef((props, ref) =>
      R.createElement(
        'div',
        { 'data-testid': 'file-upload' },
        props.children,
        R.createElement('input', {
          ref,
          multiple: true,
          type: 'file',
          'data-testid': 'file-input',
          onChange: props.handleFileChange,
        }),
      ),
    ),
    TooltipAnchor: (props) => props.render,
    AttachmentIcon: () => R.createElement('span', { 'data-testid': 'attachment-icon' }),
  };
});

const mockUseAgentToolPermissions = jest.requireMock('~/hooks').useAgentToolPermissions;
const mockUseAgentCapabilities = jest.requireMock('~/hooks').useAgentCapabilities;
const mockUseGetAgentsConfig = jest.requireMock('~/hooks').useGetAgentsConfig;
const mockUseFileHandlingNoChatContext = jest.requireMock('~/hooks').useFileHandlingNoChatContext;
const mockUseHasAccess = jest.requireMock('~/hooks').useHasAccess;
const mockUseLocalize = jest.requireMock('~/hooks').useLocalize;

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const TOOLTIP_TEXT = 'Upload a document (PDF, Word, Excel, PowerPoint, text)';

function setupMocks(
  overrides: {
    fileSearchEnabled?: boolean;
    canUseFileSearch?: boolean;
    fileSearchAllowedByAgent?: boolean;
    handleFileChange?: jest.Mock;
  } = {},
) {
  const translations: Record<string, string> = {
    com_ui_upload_file_search_tooltip: TOOLTIP_TEXT,
  };
  mockUseLocalize.mockReturnValue((key: string) => translations[key] || key);
  mockUseAgentCapabilities.mockReturnValue({
    fileSearchEnabled: overrides.fileSearchEnabled ?? true,
  });
  mockUseGetAgentsConfig.mockReturnValue({ agentsConfig: {} });
  mockUseFileHandlingNoChatContext.mockReturnValue({
    handleFileChange: overrides.handleFileChange ?? jest.fn(),
  });
  mockUseHasAccess.mockReturnValue(overrides.canUseFileSearch ?? true);
  mockUseAgentToolPermissions.mockReturnValue({
    fileSearchAllowedByAgent: overrides.fileSearchAllowedByAgent ?? false,
    codeAllowedByAgent: false,
    provider: undefined,
  });
}

function EphemeralAgentProbe({ conversationId }: { conversationId: string }) {
  const ephemeralAgent = useRecoilValue(ephemeralAgentByConvoId(conversationId));
  return <div data-testid="ephemeral-agent">{JSON.stringify(ephemeralAgent ?? null)}</div>;
}

function renderMenu(props: Record<string, unknown> = {}, { withProbe = false } = {}) {
  const conversationId = (props.conversationId as string) ?? 'test-convo';
  return render(
    <QueryClientProvider client={queryClient}>
      <RecoilRoot>
        <AttachFileMenu
          conversationId={conversationId}
          files={new Map()}
          setFiles={() => {}}
          setFilesLoading={() => {}}
          conversation={null}
          {...props}
        />
        {withProbe && <EphemeralAgentProbe conversationId={conversationId} />}
      </RecoilRoot>
    </QueryClientProvider>,
  );
}

describe('AttachFileMenu (one-click File Search upload)', () => {
  beforeEach(jest.clearAllMocks);

  describe('Rendering', () => {
    it('renders a single button with the File Search tooltip/aria-label, no dropdown', () => {
      setupMocks();
      renderMenu();
      const button = screen.getByRole('button', { name: TOOLTIP_TEXT });
      expect(button).toBeInTheDocument();
      expect(screen.queryByTestId('dropdown-menu')).not.toBeInTheDocument();
    });

    it('is disabled when disabled prop is true', () => {
      setupMocks();
      renderMenu({ disabled: true });
      expect(screen.getByRole('button', { name: TOOLTIP_TEXT })).toBeDisabled();
    });
  });

  describe('Capability/permission gating', () => {
    it('renders nothing when fileSearchEnabled capability is false', () => {
      setupMocks({ fileSearchEnabled: false });
      renderMenu();
      expect(screen.queryByRole('button', { name: TOOLTIP_TEXT })).not.toBeInTheDocument();
    });

    it('renders nothing when the user lacks the FILE_SEARCH permission', () => {
      setupMocks({ canUseFileSearch: false });
      renderMenu();
      expect(screen.queryByRole('button', { name: TOOLTIP_TEXT })).not.toBeInTheDocument();
    });

    it('shows the button for an ephemeral (non-agent) conversation regardless of fileSearchAllowedByAgent', () => {
      setupMocks({ fileSearchAllowedByAgent: false });
      renderMenu({ agentId: undefined });
      expect(screen.getByRole('button', { name: TOOLTIP_TEXT })).toBeInTheDocument();
    });

    it('hides the button for a real saved agent that does not have file_search configured', () => {
      setupMocks({ fileSearchAllowedByAgent: false });
      renderMenu({ agentId: 'agent_123' });
      expect(screen.queryByRole('button', { name: TOOLTIP_TEXT })).not.toBeInTheDocument();
    });

    it('shows the button for a real saved agent that has file_search configured', () => {
      setupMocks({ fileSearchAllowedByAgent: true });
      renderMenu({ agentId: 'agent_123' });
      expect(screen.getByRole('button', { name: TOOLTIP_TEXT })).toBeInTheDocument();
    });
  });

  describe('Upload behavior', () => {
    it('sets the input accept to document types and uploads with EToolResources.file_search on click', () => {
      setupMocks();
      const handleFileChange = jest.fn();
      mockUseFileHandlingNoChatContext.mockReturnValue({ handleFileChange });
      const file = new File(['data'], 'report.pdf', { type: 'application/pdf' });

      const originalClick = HTMLInputElement.prototype.click;
      HTMLInputElement.prototype.click = function click() {
        expect(this.accept).toContain('.pdf');
        expect(this.accept).toContain('.docx');
        expect(this.accept).toContain('.xlsx');
        expect(this.accept).toContain('.pptx');
        Object.defineProperty(this, 'files', { configurable: true, value: [file] });
        fireEvent.change(this);
      };

      try {
        renderMenu();
        fireEvent.click(screen.getByRole('button', { name: TOOLTIP_TEXT }));
      } finally {
        HTMLInputElement.prototype.click = originalClick;
      }

      expect(handleFileChange).toHaveBeenCalledWith(expect.any(Object), EToolResources.file_search);
    });

    it('sets ephemeralAgent[file_search] to true on click', () => {
      setupMocks();
      renderMenu({ conversationId: 'probe-convo' }, { withProbe: true });
      expect(screen.getByTestId('ephemeral-agent')).toHaveTextContent('null');
      fireEvent.click(screen.getByRole('button', { name: TOOLTIP_TEXT }));
      expect(screen.getByTestId('ephemeral-agent')).toHaveTextContent(
        JSON.stringify({ [EToolResources.file_search]: true }),
      );
    });

    it('activates on Enter key press', () => {
      setupMocks();
      const handleFileChange = jest.fn();
      mockUseFileHandlingNoChatContext.mockReturnValue({ handleFileChange });
      const file = new File(['data'], 'report.docx', {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      });

      const originalClick = HTMLInputElement.prototype.click;
      HTMLInputElement.prototype.click = function click() {
        Object.defineProperty(this, 'files', { configurable: true, value: [file] });
        fireEvent.change(this);
      };

      try {
        renderMenu();
        fireEvent.keyDown(screen.getByRole('button', { name: TOOLTIP_TEXT }), { key: 'Enter' });
      } finally {
        HTMLInputElement.prototype.click = originalClick;
      }

      expect(handleFileChange).toHaveBeenCalledWith(expect.any(Object), EToolResources.file_search);
    });
  });

  describe('Edge Cases', () => {
    it('handles missing agentId gracefully (treated as ephemeral)', () => {
      setupMocks();
      renderMenu({ agentId: undefined });
      expect(screen.getByRole('button', { name: TOOLTIP_TEXT })).toBeInTheDocument();
    });

    it('handles empty string agentId gracefully (treated as ephemeral)', () => {
      setupMocks();
      renderMenu({ agentId: '' });
      expect(screen.getByRole('button', { name: TOOLTIP_TEXT })).toBeInTheDocument();
    });
  });
});
