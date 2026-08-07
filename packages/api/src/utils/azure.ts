import { isEnabled } from './common';
import type { AzureOptions, GenericClient } from '~/types';

/**
 * Sanitizes the model name to be used in the URL by removing or replacing disallowed characters.
 * @param modelName - The model name to be sanitized.
 * @returns The sanitized model name.
 */
export const sanitizeModelName = (modelName: string): string => {
  // Replace periods with empty strings and other disallowed characters as needed.
  return modelName.replace(/\./g, '');
};

/**
 * Generates the Azure OpenAI API endpoint URL.
 * @param params - The parameters object.
 * @param params.azureOpenAIApiInstanceName - The Azure OpenAI API instance name.
 * @param params.azureOpenAIApiDeploymentName - The Azure OpenAI API deployment name.
 * @returns The complete endpoint URL for the Azure OpenAI API.
 */
export const genAzureEndpoint = ({
  azureOpenAIApiInstanceName,
  azureOpenAIApiDeploymentName,
}: {
  azureOpenAIApiInstanceName: string;
  azureOpenAIApiDeploymentName: string;
}): string => {
  // Support both old (.openai.azure.com) and new (.cognitiveservices.azure.com) endpoint formats
  // If instanceName already includes a full domain, use it as-is
  if (azureOpenAIApiInstanceName.includes('.azure.com')) {
    return `https://${azureOpenAIApiInstanceName}/openai/deployments/${azureOpenAIApiDeploymentName}`;
  }
  // Legacy format for backward compatibility
  return `https://${azureOpenAIApiInstanceName}.openai.azure.com/openai/deployments/${azureOpenAIApiDeploymentName}`;
};

/**
 * Generates the Azure OpenAI API chat completion endpoint URL with the API version.
 * If both deploymentName and modelName are provided, modelName takes precedence.
 * @param azureConfig - The Azure configuration object.
 * @param azureConfig.azureOpenAIApiInstanceName - The Azure OpenAI API instance name.
 * @param azureConfig.azureOpenAIApiDeploymentName - The Azure OpenAI API deployment name (optional).
 * @param azureConfig.azureOpenAIApiVersion - The Azure OpenAI API version.
 * @param modelName - The model name to be included in the deployment name (optional).
 * @param client - The API Client class for optionally setting properties (optional).
 * @returns The complete chat completion endpoint URL for the Azure OpenAI API.
 * @throws Error if neither azureOpenAIApiDeploymentName nor modelName is provided.
 */
export const genAzureChatCompletion = (
  {
    azureOpenAIApiInstanceName,
    azureOpenAIApiDeploymentName,
    azureOpenAIApiVersion,
  }: {
    azureOpenAIApiInstanceName: string;
    azureOpenAIApiDeploymentName?: string;
    azureOpenAIApiVersion: string;
  },
  modelName?: string,
  client?: GenericClient,
): string => {
  // Determine the deployment segment of the URL based on provided modelName or azureOpenAIApiDeploymentName
  let deploymentSegment: string;
  if (isEnabled(process.env.AZURE_USE_MODEL_AS_DEPLOYMENT_NAME) && modelName) {
    const sanitizedModelName = sanitizeModelName(modelName);
    deploymentSegment = sanitizedModelName;
    if (client && typeof client === 'object') {
      client.azure.azureOpenAIApiDeploymentName = sanitizedModelName;
    }
  } else if (azureOpenAIApiDeploymentName) {
    deploymentSegment = azureOpenAIApiDeploymentName;
  } else if (!process.env.AZURE_OPENAI_BASEURL) {
    throw new Error(
      'Either a model name with the `AZURE_USE_MODEL_AS_DEPLOYMENT_NAME` setting or a deployment name must be provided if `AZURE_OPENAI_BASEURL` is omitted.',
    );
  } else {
    deploymentSegment = '';
  }

  return `https://${azureOpenAIApiInstanceName}.openai.azure.com/openai/deployments/${deploymentSegment}/chat/completions?api-version=${azureOpenAIApiVersion}`;
};

/**
 * Retrieves the Azure OpenAI API credentials from environment variables.
 * @returns An object containing the Azure OpenAI API credentials.
 */
export const getAzureCredentials = (): AzureOptions => {
  return {
    azureOpenAIApiKey: process.env.AZURE_API_KEY ?? process.env.AZURE_OPENAI_API_KEY,
    azureOpenAIApiInstanceName: process.env.AZURE_OPENAI_API_INSTANCE_NAME,
    azureOpenAIApiDeploymentName: process.env.AZURE_OPENAI_API_DEPLOYMENT_NAME,
    azureOpenAIApiVersion: process.env.AZURE_OPENAI_API_VERSION,
  };
};

/**
 * Constructs a URL by replacing placeholders in the baseURL with values from the azure object.
 * It specifically looks for '${INSTANCE_NAME}' and '${DEPLOYMENT_NAME}' within the baseURL and replaces
 * them with 'azureOpenAIApiInstanceName' and 'azureOpenAIApiDeploymentName' from the azure object.
 * If the respective azure property is not provided, the placeholder is replaced with an empty string.
 *
 * @param params - The parameters object.
 * @param params.baseURL - The baseURL to inspect for replacement placeholders.
 * @param params.azureOptions - The azure options object containing the instance and deployment names.
 * @returns The complete baseURL with credentials injected for the Azure OpenAI API.
 */
export function constructAzureURL({
  baseURL,
  azureOptions,
}: {
  baseURL: string;
  azureOptions?: AzureOptions;
}): string {
  let finalURL = baseURL;

  // Replace INSTANCE_NAME and DEPLOYMENT_NAME placeholders with actual values if available
  if (azureOptions) {
    finalURL = finalURL.replace('${INSTANCE_NAME}', azureOptions.azureOpenAIApiInstanceName ?? '');
    finalURL = finalURL.replace(
      '${DEPLOYMENT_NAME}',
      azureOptions.azureOpenAIApiDeploymentName ?? '',
    );
  }

  return finalURL;
}

/** Shape of the structured fields Azure/LiteLLM attach to a content-filter rejection */
interface AzureContentFilterErrorLike {
  code?: string;
  status?: number;
  message?: string;
  innererror?: { code?: string };
  error?: {
    code?: string;
    message?: string;
    innererror?: { code?: string; content_filter_result?: unknown };
    content_filter_result?: unknown;
  };
  content_filter_result?: unknown;
  response?: { data?: { error?: { message?: string } } };
}

const isFilterResult = (value: unknown): boolean => typeof value === 'object' && value != null;

/**
 * Fixed, non-config-derived identifiers that only ever appear in a genuine content-filter
 * rejection: Azure's own compliance copy and LiteLLM's dedicated exception class name. Unlike
 * model/model-group names (which are config-driven and change per environment), these strings
 * are hardcoded in Azure OpenAI and LiteLLM themselves, so matching them is stable across envs.
 * Needed because once LiteLLM exhausts its configured fallbacks, it flattens the original
 * structured Azure error (code/innererror/content_filter_result) into a single message string,
 * so the structured-field checks below no longer have anything to match on.
 */
const CONTENT_FILTER_MESSAGE_MARKERS = [
  'ContentPolicyViolationError',
  'ResponsibleAIPolicyViolation',
  // Anchored to Azure's full phrase on purpose. Matching the bare words "content management
  // policy" would also fire on any upstream error that happens to quote request context back —
  // context-length errors quote the offending messages, guardrail and proxy errors echo params —
  // so a benign failure could be reported to the user as a policy violation. That is the worse
  // direction to be wrong in, and the other two markers are vendor-specific identifiers that
  // cannot appear by accident.
  "Azure OpenAI's content management policy",
];

/**
 * Detects whether an error thrown by the LLM provider (surfaced through LiteLLM/Azure OpenAI)
 * represents a content-filter rejection. Prefers Azure's structured `code`/`innererror.code`
 * fields, falling back to fixed LiteLLM/Azure identifiers embedded in the message when LiteLLM
 * has flattened the structured error away (e.g. after exhausting its fallback chain) — never to
 * fragile substring matching on model group names, which are config-driven and will change.
 * @param error - The error thrown by the upstream provider/SDK.
 * @returns Whether the error is an Azure content-filter rejection.
 */
export function isAzureContentFilterError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }

  const err = error as AzureContentFilterErrorLike;
  const nested = err.error;

  if (
    err.code === 'content_filter' ||
    nested?.code === 'content_filter' ||
    err.innererror?.code === 'ResponsibleAIPolicyViolation' ||
    nested?.innererror?.code === 'ResponsibleAIPolicyViolation' ||
    // Azure's real body nests this under error.innererror.content_filter_result; the other two
    // locations are kept because LiteLLM and the SDKs reshape errors between us and Azure.
    (err.status === 400 &&
      (isFilterResult(nested?.innererror?.content_filter_result) ||
        isFilterResult(err.content_filter_result) ||
        isFilterResult(nested?.content_filter_result)))
  ) {
    return true;
  }

  // Scan every place the human-readable text can land. LiteLLM's proxy returns an OpenAI-style
  // envelope with the text at `error.message`, and whether it is hoisted to a top-level `message`
  // depends on which client layer wrapped it — openai-node's APIError hoists, an agents/LangChain
  // wrapper may not. Checking only the top level silently drops back to the raw dump.
  const candidates = [err.message, nested?.message, err.response?.data?.error?.message];

  return candidates.some(
    (text) =>
      typeof text === 'string' &&
      CONTENT_FILTER_MESSAGE_MARKERS.some((marker) => text.includes(marker)),
  );
}
