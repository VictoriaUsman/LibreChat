# ROMTech Internal AI Chatbot  
## Phase 0 Proof of Concept Plan

**Purpose:**  
Build a thin proof of concept to validate the core architecture for an internal ROMTech ChatGPT-style assistant before moving into a fuller v1 build.

This Phase 0 effort is not intended to be production-ready. The goal is to prove that the major pieces can work together, identify configuration gaps, and answer the technical questions needed before committing to the next phase.

---

## Prerequisites and Known Constraints

**Infrastructure target:** Azure Container Apps (non-production environment). Docker is not permitted; all containers must run in Azure Container Apps.

**Azure OpenAI:** The team will configure an Azure OpenAI test endpoint and point the application to it. This is not expected to be a blocker and should be straightforward to set up.

**Okta:** Configuring Okta authentication requires coordination with the Okta admin in a separate department. This should be engaged early in the build sequence as it is a dependency that is outside the team's direct control.

**Next step after Phase 0:** If Phase 0 is successful, the team will move directly into v1 planning. The output of Phase 0 feeds a PBI backlog — the intent is to move forward, not to stop and address accumulated tech debt.

---

## 1. Phase 0 Goal

Phase 0 should prove the following end-to-end flow:

```text
Okta-authenticated user
  ↓
LibreChat
  ↓
LiteLLM
  ↓
Azure OpenAI model
  ↓
Streaming response back to user
```

At the end of Phase 0, the team should be able to answer:

> Can we use LibreChat as the internal chat UI, place LiteLLM between LibreChat and Azure OpenAI, authenticate users through Okta, persist conversations, and control model access well enough to move toward v1?

---

## 2. What We Are Building

Build a minimal, non-production implementation of the proposed architecture.

### Required Components

```text
LibreChat
- User-facing ChatGPT-style application
- Handles chat UI, conversations, message context, and user interaction

LiteLLM
- Gateway between LibreChat and Azure OpenAI
- Handles model routing, model allowlisting, cost/usage tracking, and rate/budget controls

Azure OpenAI
- Provides the actual model responses

Okta
- Provides authentication into the application

Database / Storage
- Conversation persistence for LibreChat
- LiteLLM state storage if required
```

---

## 3. Phase 0 Scope

### In Scope

- Stand up LibreChat in a non-production environment.
- Stand up LiteLLM in front of Azure OpenAI.
- Configure LibreChat to call LiteLLM instead of Azure OpenAI directly.
- Configure a small set of OpenAI models through LiteLLM.
- Validate streaming responses.
- Validate conversation history/persistence.
- Validate Okta authentication.
- Validate basic user/team usage tracking if possible.
- Validate basic model allowlisting.
- Validate basic rate limit or budget enforcement.
- Identify which LibreChat features should be enabled or disabled for v1.
- Document gaps, risks, and required decisions for v1.

### Out of Scope

- Full production deployment.
- Full branding/theming.
- Enterprise-wide rollout.
- Broad internal document RAG.
- Advanced file/document workflows.
- Web search.
- Image generation.
- Code interpreter.
- MCP/tool/plugin integrations.
- Complex DLP workflows.
- Detailed BAA/service coverage review.

---

## 4. Key Questions to Answer

### A. LibreChat Fit

1. Does LibreChat provide a good enough ChatGPT-style user experience for ROMTech employees?
2. Can unwanted features be disabled or hidden?
3. Can the available model list be controlled?
4. Can system prompts or default assistant instructions be configured?
5. Can users create, continue, rename, and delete conversations?
6. Are there any UI or functional gaps that would block v1?

**Expected Output:**  
A short gap list marking each issue as:

```text
Acceptable for v1
Needs configuration
Needs customization
Blocker
```

---

### B. LibreChat Deployment

1. Can LibreChat run successfully in our chosen non-production environment?
2. What deployment approach works best for v1?
3. What environment variables/configuration are required?
4. What persistent storage does LibreChat require?
5. Does conversation history survive application restarts?

**Expected Output:**  
A documented deployment path and required configuration list.

---

### C. LiteLLM Integration

1. Can LibreChat call LiteLLM as an OpenAI-compatible endpoint?
2. Can LiteLLM route requests to the configured Azure OpenAI models?
3. Does streaming work through LiteLLM?
4. Do errors from Azure OpenAI flow back cleanly through LiteLLM and LibreChat?
5. Can LiteLLM enforce a model allowlist?
6. Can LiteLLM track usage by model and, if possible, by user/team?
7. Can LiteLLM enforce a simple rate limit or test budget?

**Expected Output:**  
A working LibreChat → LiteLLM → Azure OpenAI request path.

---

### D. Okta Authentication

1. Can users log into LibreChat using Okta?
2. Can access be limited to a test/pilot group?
3. Does the Okta tile launch the application cleanly?
4. Do user identity claims such as email/name flow into LibreChat?
5. Can group claims be used later for role/model/feature control?

**Expected Output:**  
A working Okta login flow for a small test group.

---

### E. Conversation Context and Persistence

1. How does LibreChat decide which prior messages are sent as context?
2. Can the context behavior be configured?
3. Are conversations saved correctly?
4. Can users delete conversations?
5. Where exactly is conversation data stored?
6. What data is stored per message?

**Expected Output:**  
A short data-flow note explaining how conversation messages are stored and reused.

---

### F. Model Control

1. Can we expose only the approved OpenAI models we want users to access?
2. Can model names be made user-friendly, such as:

```text
ROMTech AI Standard
ROMTech AI Fast
```

3. What happens if a user or client attempts to call a model not configured in LiteLLM?
4. Can the default model be controlled?

**Expected Output:**  
A working model allowlist and a recommended v1 model configuration.

---

### G. Usage, Cost, and Operations

1. Can LiteLLM show usage by model?
2. Can LiteLLM show token usage?
3. Can LiteLLM estimate or track cost?
4. Can we associate usage with users, groups, departments, or virtual keys?
5. What operational dashboard or logs are available out of the box?
6. What would need to be added for v1?

**Expected Output:**  
A basic usage/cost tracking assessment.

---

### H. Feature Decisions for v1

For each feature, determine whether it should be enabled, disabled, or deferred.

| Feature | Phase 0 Action | Likely v1 Recommendation |
|---|---:|---:|
| Basic chat | Test | Enable |
| Streaming responses | Test | Enable |
| Conversation history | Test | Enable |
| Okta login | Test | Enable |
| Model picker | Test | Limit to approved models |
| File upload | Investigate only | Defer or restrict |
| Web search | Do not enable | Defer |
| Image input | Do not enable | Defer |
| Image generation | Do not enable | Defer |
| Code interpreter | Do not enable | Defer |
| MCP/tools/plugins | Do not enable | Defer |
| RAG/internal documents | Do not build | Later phase |

**Expected Output:**  
A v1 feature recommendation table.

---

## 5. Acceptance Criteria

Phase 0 is considered successful if the team can demonstrate:

1. A user can open the proof of concept and authenticate through Okta.
2. The user can send a message in LibreChat.
3. LibreChat sends the request to LiteLLM, not directly to Azure OpenAI.
4. LiteLLM routes the request to an Azure OpenAI model.
5. The response streams back into LibreChat.
6. Conversation history is saved and can be reopened.
7. Only configured models are available.
8. An unconfigured model request is rejected or unavailable.
9. Basic usage/token data is visible in LiteLLM or logs.
10. The team has documented gaps and recommendations for v1.

---

## 6. Phase 0 Deliverables

At the end of Phase 0, the team should produce:

### 1. Working Proof of Concept

A non-production demo showing:

```text
Okta → LibreChat → LiteLLM → Azure OpenAI → streamed response
```

### 2. Architecture Notes

A short explanation of:

- Where LibreChat runs
- Where LiteLLM runs
- What database/storage is used
- How requests flow between components
- Where model configuration lives

### 3. Configuration Notes

Document:

- Required environment variables
- LibreChat endpoint configuration
- LiteLLM model configuration
- Okta/OIDC configuration
- Database/storage configuration

### 4. Feature Recommendation Table

Document which features should be:

```text
Enabled for v1
Disabled for v1
Deferred to later phase
```

### 5. Gaps and Risks List

Document any issues found during Phase 0, including:

- LibreChat limitations
- LiteLLM integration issues
- Okta integration issues
- Deployment concerns
- Feature restrictions
- Operational gaps

Each item should be marked as:

```text
Acceptable for v1
Fix before v1
Needs stakeholder decision
Blocker
```

### 6. V1 Recommendation and PBI Handoff

End Phase 0 with one of the following recommendations:

```text
Proceed to v1 build.

Proceed to v1 build after listed fixes.

Do not proceed with this stack; evaluate alternatives.
```

If the recommendation is to proceed, the Phase 0 findings — including the gap list, feature recommendation table, and configuration notes — feed directly into v1 PBI creation. The intent is to move forward into v1 planning without a tech debt cleanup phase between Phase 0 and v1.

---

## 7. Recommended Build Order

1. Configure Azure OpenAI test endpoint and confirm it is accessible.
2. Stand up LiteLLM in Azure Container Apps (non-prod).
3. Confirm LiteLLM can call Azure OpenAI.
4. Stand up LibreChat in Azure Container Apps (non-prod).
5. Configure LibreChat to call LiteLLM.
6. Confirm end-to-end chat and streaming.
7. Add conversation persistence.
8. Add Okta authentication — coordinate early with the Okta admin in the separate department, as this is an external dependency.
9. Test model allowlisting.
10. Test basic usage tracking.
11. Review which features are enabled by default.
12. Produce Phase 0 findings and v1 recommendation.

---

## 8. Final Phase 0 Summary

Phase 0 is intentionally thin. We are not building the full internal AI assistant yet.

We are proving the foundation:

```text
Can LibreChat be our internal ChatGPT-style app?
Can LiteLLM be our control layer?
Can Azure OpenAI provide the model responses?
Can Okta control access?
Can conversations persist?
Can we control which models and features are available?
```

If the answer is yes, the team can move into v1 with confidence and a much clearer understanding of the real implementation work.
