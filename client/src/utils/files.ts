import {
  TextPaths,
  FilePaths,
  CodePaths,
  AudioPaths,
  VideoPaths,
  SheetPaths,
} from '@librechat/client';
import {
  megabyte,
  QueryKeys,
  inferMimeType,
  excelMimeTypes,
  EToolResources,
  fileConfig as defaultFileConfig,
} from 'librechat-data-provider';
import type { TFile, EndpointFileConfig, FileConfig } from 'librechat-data-provider';
import type { QueryClient } from '@tanstack/react-query';
import type { ExtendedFile } from '~/common';

export const partialTypes = ['text/x-'];

const textDocument = {
  paths: TextPaths,
  fill: '#FF5588',
  title: 'Document',
};

const spreadsheet = {
  paths: SheetPaths,
  fill: '#10A37F',
  title: 'Spreadsheet',
};

const codeFile = {
  paths: CodePaths,
  fill: '#FF6E3C',
  // TODO: make this dynamic to the language
  title: 'Code',
};

const artifact = {
  paths: CodePaths,
  fill: '#2D305C',
  title: 'Code',
};

const audioFile = {
  paths: AudioPaths,
  fill: '#FF6B35',
  title: 'Audio',
};

const videoFile = {
  paths: VideoPaths,
  fill: '#8B5CF6',
  title: 'Video',
};

export const fileTypes = {
  /* Category matches */
  file: {
    paths: FilePaths,
    fill: '#0000FF',
    title: 'File',
  },
  text: textDocument,
  txt: textDocument,
  audio: audioFile,
  video: videoFile,
  // application:,

  /* Partial matches */
  csv: spreadsheet,
  'application/pdf': textDocument,
  pdf: textDocument,
  'text/x-': codeFile,
  artifact: artifact,

  /* Exact matches */
  // 'application/json':,
  // 'text/html':,
  // 'text/css':,
  // image,
};

// export const getFileType = (type = '') => {
//   let fileType = fileTypes.file;
//   const exactMatch = fileTypes[type];
//   const partialMatch = !exactMatch && partialTypes.find((type) => type.includes(type));
//   const category = (!partialMatch && (type.split('/')[0] ?? 'text') || 'text');

//   if (exactMatch) {
//     fileType = exactMatch;
//   } else if (partialMatch) {
//     fileType = fileTypes[partialMatch];
//   } else if (fileTypes[category]) {
//     fileType = fileTypes[category];
//   }

//   if (!fileType) {
//     fileType = fileTypes.file;
//   }

//   return fileType;
// };

export const getFileType = (
  type = '',
): {
  paths: React.FC;
  fill: string;
  title: string;
} => {
  // Direct match check
  if (fileTypes[type]) {
    return fileTypes[type];
  }

  if (excelMimeTypes.test(type)) {
    return spreadsheet;
  }

  // Partial match check
  const partialMatch = partialTypes.find((partial) => type.includes(partial));
  if (partialMatch && fileTypes[partialMatch]) {
    return fileTypes[partialMatch];
  }

  // Category check
  const category = type.split('/')[0] || 'text';
  if (fileTypes[category]) {
    return fileTypes[category];
  }

  // Default file type
  return fileTypes.file;
};

/**
 * Format a date string to a human readable format
 * @example
 * formatDate('2020-01-01T00:00:00.000Z') // '1 Jan 2020'
 */
export function formatDate(dateString: string, isSmallScreen = false) {
  if (!dateString) {
    return '';
  }

  const date = new Date(dateString);

  if (isSmallScreen) {
    return date.toLocaleDateString('en-US', {
      month: 'numeric',
      day: 'numeric',
      year: '2-digit',
    });
  }

  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  const day = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();

  return `${day} ${month} ${year}`;
}

/**
 * Adds a file to the query cache
 */
export function addFileToCache(queryClient: QueryClient, newfile: TFile) {
  const currentFiles = queryClient.getQueryData<TFile[]>([QueryKeys.files]);

  if (!currentFiles) {
    console.warn('No current files found in cache, skipped updating file query cache');
    return;
  }

  const fileIndex = currentFiles.findIndex((file) => file.file_id === newfile.file_id);

  if (fileIndex > -1) {
    console.warn('File already exists in cache, skipped updating file query cache');
    return;
  }

  queryClient.setQueryData<TFile[]>(
    [QueryKeys.files],
    [
      {
        ...newfile,
      },
      ...currentFiles,
    ],
  );
}

export function formatBytes(bytes: number, decimals = 2) {
  if (bytes === 0) {
    return 0;
  }
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm));
}

const { checkType } = defaultFileConfig;

export const validateFiles = ({
  files,
  fileList,
  setError,
  endpointFileConfig,
  toolResource,
  fileConfig,
}: {
  fileList: File[];
  files: Map<string, ExtendedFile>;
  setError: (error: string) => void;
  endpointFileConfig: EndpointFileConfig;
  toolResource?: string;
  fileConfig: FileConfig | null;
}) => {
  const { fileLimit, fileSizeLimit, totalSizeLimit, supportedMimeTypes, disabled } =
    endpointFileConfig;
  /** Block all uploads if the endpoint is explicitly disabled */
  if (disabled === true) {
    setError('com_ui_attach_error_disabled');
    return false;
  }
  const existingFiles = Array.from(files.values());
  const incomingTotalSize = fileList.reduce((total, file) => total + file.size, 0);
  if (incomingTotalSize === 0) {
    setError('com_error_files_empty');
    return false;
  }
  const currentTotalSize = existingFiles.reduce((total, file) => total + file.size, 0);

  if (fileLimit && fileList.length + files.size > fileLimit) {
    setError(`File limit reached: ${fileLimit} files`);
    return false;
  }

  for (let i = 0; i < fileList.length; i++) {
    let originalFile = fileList[i];
    const fileType = inferMimeType(originalFile.name, originalFile.type);

    // Check if the file type is still empty after the extension check
    if (!fileType) {
      setError('Unable to determine file type for: ' + originalFile.name);
      return false;
    }

    // Replace empty type with inferred type
    if (originalFile.type !== fileType) {
      const newFile = new File([originalFile], originalFile.name, { type: fileType });
      originalFile = newFile;
      fileList[i] = newFile;
    }

    // Note: file_search intentionally has no dedicated branch here — it uses the
    // endpoint's own `supportedMimeTypes` (the same admin-configured allowlist every
    // other upload on this endpoint is checked against), so client validation can
    // never diverge from what the server actually accepts. This assumes the endpoint's
    // configured supportedMimeTypes excludes non-document types (images/video/audio);
    // see the "MUST be scoped" comment on fileConfig.endpoints in librechat.yaml.
    let mimeTypesToCheck = supportedMimeTypes;
    if (toolResource === EToolResources.context) {
      mimeTypesToCheck = [
        ...(fileConfig?.text?.supportedMimeTypes || []),
        ...(fileConfig?.ocr?.supportedMimeTypes || []),
        ...(fileConfig?.stt?.supportedMimeTypes || []),
      ];
    }

    if (!checkType(originalFile.type, mimeTypesToCheck)) {
      setError(`Unsupported file type: ${originalFile.type}`);
      return false;
    }

    if (fileSizeLimit && originalFile.size >= fileSizeLimit) {
      setError(`File size limit exceeded: ${fileSizeLimit / megabyte} MB`);
      return false;
    }
  }

  if (totalSizeLimit && currentTotalSize + incomingTotalSize > totalSizeLimit) {
    setError(`Total file size limit exceeded: ${totalSizeLimit / megabyte} MB`);
    return false;
  }

  const combinedFilesInfo = [
    ...existingFiles.map(
      (file) =>
        `${file.file?.name ?? file.filename}-${file.size}-${file.type?.split('/')[0] ?? 'file'}`,
    ),
    ...fileList.map(
      (file: File | undefined) =>
        `${file?.name}-${file?.size}-${file?.type.split('/')[0] ?? 'file'}`,
    ),
  ];

  const uniqueFilesSet = new Set(combinedFilesInfo);

  if (uniqueFilesSet.size !== combinedFilesInfo.length) {
    setError('com_error_files_dupe');
    return false;
  }

  return true;
};

const literalMimeTypePattern = /^[\w.+-]+\/[\w.+-]+$/;

/**
 * Best-effort conversion of a `supportedMimeTypes` regex list back into a literal,
 * comma-separated string for an `<input accept>` attribute. Only regexes that reduce to
 * a single literal "type/subtype" (as produced for admin-configured, one-type-per-entry
 * `librechat.yaml` lists) are included; bundled alternation regexes (e.g. the built-in
 * defaults covering many legacy MIME aliases at once) don't cleanly reduce to one literal
 * type and are skipped here. This only narrows the OS picker's hint — `validateFiles` is
 * the real enforcement and checks the full regex list regardless of what this omits.
 */
export const mimeTypesToAcceptString = (mimeTypes?: RegExp[]): string => {
  if (!mimeTypes || mimeTypes.length === 0) {
    return '';
  }
  return (
    mimeTypes
      // `.source` always renders "/" as "\/" (regardless of how the RegExp was
      // constructed), so undo that before checking for a plain "type/subtype" literal.
      .map((regex) => regex.source.replace(/\\\//g, '/'))
      .filter((source) => literalMimeTypePattern.test(source))
      .join(',')
  );
};

export function sortPagesByRelevance(
  pages: number[],
  pageRelevance: Record<number, number>,
): number[] {
  if (!pageRelevance || Object.keys(pageRelevance).length === 0) {
    return pages;
  }
  return [...pages].sort((a, b) => (pageRelevance[b] || 0) - (pageRelevance[a] || 0));
}
