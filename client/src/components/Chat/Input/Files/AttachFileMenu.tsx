import React, { useRef } from 'react';
import { useSetRecoilState } from 'recoil';
import { FileUpload, TooltipAnchor, AttachmentIcon } from '@librechat/client';
import {
  EToolResources,
  PermissionTypes,
  Permissions,
  defaultAgentCapabilities,
} from 'librechat-data-provider';
import type { EModelEndpoint, EndpointFileConfig, TConversation } from 'librechat-data-provider';
import type { ExtendedFile, FileSetter } from '~/common';
import {
  useAgentToolPermissions,
  useAgentCapabilities,
  useGetAgentsConfig,
  useFileHandlingNoChatContext,
  useHasAccess,
  useLocalize,
} from '~/hooks';
import { ephemeralAgentByConvoId } from '~/store';
import { isEphemeralAgent } from '~/common';
import { cn, mimeTypesToAcceptString } from '~/utils';

interface AttachFileMenuProps {
  agentId?: string | null;
  disabled?: boolean | null;
  conversationId: string;
  endpointType?: EModelEndpoint | string;
  endpointFileConfig?: EndpointFileConfig;
  useResponsesApi?: boolean;
  files: Map<string, ExtendedFile>;
  setFiles: FileSetter;
  setFilesLoading: React.Dispatch<React.SetStateAction<boolean>>;
  conversation: TConversation | null;
}

const AttachFileMenu = ({
  agentId,
  disabled,
  conversationId,
  endpointFileConfig,
  files,
  setFiles,
  setFilesLoading,
  conversation,
}: AttachFileMenuProps) => {
  const localize = useLocalize();
  const isUploadDisabled = disabled ?? false;
  const inputRef = useRef<HTMLInputElement>(null);
  const setEphemeralAgent = useSetRecoilState(ephemeralAgentByConvoId(conversationId));
  const { handleFileChange } = useFileHandlingNoChatContext(undefined, {
    files,
    setFiles,
    setFilesLoading,
    conversation,
  });

  const { agentsConfig } = useGetAgentsConfig();
  const capabilities = useAgentCapabilities(agentsConfig?.capabilities ?? defaultAgentCapabilities);
  const { fileSearchAllowedByAgent } = useAgentToolPermissions(agentId, undefined);
  const canUseFileSearch = useHasAccess({
    permissionType: PermissionTypes.FILE_SEARCH,
    permission: Permissions.USE,
  });

  const canShowFileSearchUpload =
    capabilities.fileSearchEnabled &&
    canUseFileSearch &&
    (isEphemeralAgent(agentId) || fileSearchAllowedByAgent);

  if (!canShowFileSearchUpload) {
    return null;
  }

  const tooltipText = localize('com_ui_upload_file_search_tooltip');

  return (
    <FileUpload
      ref={inputRef}
      handleFileChange={(e) => handleFileChange(e, EToolResources.file_search)}
    >
      <TooltipAnchor
        description={tooltipText}
        id="attach-file-menu-button"
        disabled={isUploadDisabled}
        render={
          <button
            type="button"
            id="attach-file-menu-button"
            aria-label={tooltipText}
            disabled={isUploadDisabled}
            className={cn(
              'flex size-9 items-center justify-center rounded-full p-1 transition-colors hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-opacity-50',
            )}
            onClick={() => {
              if (!inputRef.current) {
                return;
              }
              setEphemeralAgent((prev) => ({ ...prev, [EToolResources.file_search]: true }));
              inputRef.current.value = '';
              inputRef.current.accept = mimeTypesToAcceptString(
                endpointFileConfig?.supportedMimeTypes,
              );
              inputRef.current.click();
            }}
          >
            <div className="flex w-full items-center justify-center gap-2">
              <AttachmentIcon />
            </div>
          </button>
        }
      />
    </FileUpload>
  );
};

export default React.memo(AttachFileMenu);
