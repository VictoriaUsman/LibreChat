/**
 * Tests for abortMiddleware - handleAbortError text sanitization.
 *
 * Covers ROMCHAT-BUG-002: Azure/LiteLLM content-filter rejections must be
 * substituted with a generic `{"type":"content_filter"}` payload instead of
 * leaking the raw upstream error (internal model group names, fallback
 * routing config, full content_filter_result payload) to the client.
 *
 * Also verifies the pre-existing INVALID_REQUEST / NO_SYSTEM_MESSAGES / generic
 * fallback branches keep behaving exactly as before.
 */

const mockSendError = jest.fn().mockResolvedValue();

jest.mock('@librechat/data-schemas', () => ({
  logger: {
    debug: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    info: jest.fn(),
  },
}));

jest.mock('@librechat/api', () => ({
  countTokens: jest.fn().mockResolvedValue(100),
  isEnabled: jest.fn().mockReturnValue(false),
  sendEvent: jest.fn(),
  GenerationJobManager: {
    abortJob: jest.fn(),
  },
  recordCollectedUsage: jest.fn(),
  sanitizeMessageForTransmit: jest.fn((msg) => msg),
  // Stand-in for the real detector in packages/api/src/utils/azure.ts. It is duplicated rather
  // than required because `@librechat/api` resolves to a built dist bundle, and requiring it here
  // pulls the whole module graph into a middleware unit test.
  //
  // ⚠️ IT MUST STAY COMPLETE. An earlier version kept only the four structured-field checks and
  // dropped the message-marker fallback — the half that PATCHES.md identifies as the one that
  // actually fires in production, since LiteLLM flattens the structured Azure error away once its
  // fallback chain is exhausted. That made this suite pass on a shape that never reaches us while
  // never exercising the shape that does. Behavioural coverage of the detector itself lives in
  // packages/api/src/utils/azure.spec.ts; what this file proves is the WIRING — that a detected
  // rejection reaches the client as the generic typed payload.
  isAzureContentFilterError: (error) => {
    if (!error || typeof error !== 'object') {
      return false;
    }
    const nested = error.error;
    const isFilterResult = (value) => typeof value === 'object' && value != null;

    if (
      error.code === 'content_filter' ||
      nested?.code === 'content_filter' ||
      error.innererror?.code === 'ResponsibleAIPolicyViolation' ||
      nested?.innererror?.code === 'ResponsibleAIPolicyViolation' ||
      (error.status === 400 &&
        (isFilterResult(nested?.innererror?.content_filter_result) ||
          isFilterResult(error.content_filter_result) ||
          isFilterResult(nested?.content_filter_result)))
    ) {
      return true;
    }

    const markers = [
      'ContentPolicyViolationError',
      'ResponsibleAIPolicyViolation',
      "Azure OpenAI's content management policy",
    ];
    return [error.message, nested?.message, error.response?.data?.error?.message].some(
      (text) => typeof text === 'string' && markers.some((marker) => text.includes(marker)),
    );
  },
}));

jest.mock('librechat-data-provider', () => ({
  isAssistantsEndpoint: jest.fn().mockReturnValue(false),
  ErrorTypes: {
    INVALID_REQUEST: 'invalid_request_error',
    NO_SYSTEM_MESSAGES: 'no_system_messages',
    CONTENT_FILTER: 'content_filter',
  },
}));

jest.mock('~/app/clients/prompts', () => ({
  truncateText: jest.fn((text) => text),
  smartTruncateText: jest.fn((text) => text),
}));

jest.mock('~/cache/clearPendingReq', () => jest.fn().mockResolvedValue());

jest.mock('~/server/middleware/error', () => ({
  sendError: (...args) => mockSendError(...args),
}));

jest.mock('~/models', () => ({
  saveMessage: jest.fn().mockResolvedValue(),
  getConvo: jest.fn().mockResolvedValue({ title: 'Test Chat' }),
}));

jest.mock('./abortRun', () => ({
  abortRun: jest.fn(),
}));

const { handleAbortError } = require('./abortMiddleware');

describe('abortMiddleware - handleAbortError', () => {
  const req = { body: {}, user: { id: 'user-123' } };
  const res = { headersSent: false };
  const data = {
    sender: 'AI',
    conversationId: 'convo-123',
    messageId: 'msg-123',
    parentMessageId: 'parent-123',
    userMessageId: 'user-msg-123',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('sanitizes an Azure content-filter rejection to a generic type payload', async () => {
    const error = new Error(
      "litellm.BadRequestError: AzureException BadRequestError - model_group: ROMTech AI Fast Backup - {'error': {'code': 'content_filter'}}",
    );
    error.code = 'content_filter';

    await handleAbortError(res, req, error, data);

    expect(mockSendError).toHaveBeenCalledTimes(1);
    const options = mockSendError.mock.calls[0][2];
    expect(options.text).toBe('{"type":"content_filter"}');
    expect(options.text).not.toMatch(/ROMTech/);
  });

  it('still sanitizes when the content-filter error also carries type: invalid_request_error', async () => {
    const error = new Error('{"error":{"type":"invalid_request_error","code":"content_filter"}}');
    error.type = 'invalid_request_error';
    error.code = 'content_filter';

    await handleAbortError(res, req, error, data);

    const options = mockSendError.mock.calls[0][2];
    expect(options.text).toBe('{"type":"content_filter"}');
  });

  it('sanitizes the flattened LiteLLM error that survives an exhausted fallback chain', async () => {
    // The shape that actually reaches us in production: by the time LiteLLM has retried the
    // primary and failed over to the backup deployment, Azure's structured code / innererror /
    // content_filter_result fields are gone and only this message string remains. If the
    // detector ever loses its message-marker fallback, THIS is the test that must fail.
    const error = new Error(
      'litellm.BadRequestError: litellm.ContentPolicyViolationError: The response was filtered ' +
        "due to the prompt triggering Azure OpenAI's content management policy. Please modify " +
        'your prompt and retry. model=ROMTech AI Fast. content_policy_fallback=None. ' +
        "fallbacks=[{'ROMTech AI Fast': ['ROMTech AI Fast Backup']}]. No fallback model group " +
        'found for original model_group=ROMTech AI Fast Backup.',
    );

    await handleAbortError(mockRes, mockReq, error, { conversationId: 'abc' });

    const [, options] = mockSendError.mock.calls[0];
    expect(options.text).toBe('{"type":"content_filter"}');
    // The whole point: no model group, deployment or fallback table reaches the user.
    expect(options.text).not.toMatch(/ROMTech|fallback|litellm|model_group/i);
  });

  it('does not leak an unrelated upstream error to the user', async () => {
    // A 429 or auth failure carries the same LiteLLM envelope as the content-filter case, so it
    // leaks the same internal names if it is passed through verbatim.
    const error = new Error(
      'litellm.RateLimitError: AzureException - Requests to the ChatCompletions_Create ' +
        'Operation under Azure OpenAI API have exceeded token rate limit of your current ' +
        'AIServices S0 pricing tier. model_group=ROMTech AI Standard Backup.',
    );

    await handleAbortError(mockRes, mockReq, error, { conversationId: 'abc' });

    const [, options] = mockSendError.mock.calls[0];
    expect(options.text).not.toMatch(/ROMTech|model_group|AIServices/i);
  });

  it('leaves the existing INVALID_REQUEST branch unaffected', async () => {
    const error = new Error('some upstream invalid request message');
    error.type = 'invalid_request_error';

    await handleAbortError(res, req, error, data);

    const options = mockSendError.mock.calls[0][2];
    expect(options.text).toBe('{"type":"invalid_request_error"}');
  });

  it('leaves the existing NO_SYSTEM_MESSAGES branch unaffected', async () => {
    const error = new Error("Model does not support 'system' role messages");

    await handleAbortError(res, req, error, data);

    const options = mockSendError.mock.calls[0][2];
    expect(options.text).toBe('{"type":"no_system_messages"}');
  });

  it('falls back to the generic admin-contact message for unrecognized errors', async () => {
    const error = new Error('some unrelated failure');

    await handleAbortError(res, req, error, data);

    const options = mockSendError.mock.calls[0][2];
    expect(options.text).toBe(
      'An error occurred while processing your request. Please contact the Admin.',
    );
  });
});
