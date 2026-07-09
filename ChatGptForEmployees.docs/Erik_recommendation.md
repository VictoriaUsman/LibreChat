# ROMTech Internal AI Chatbot — Analysis and Recommended Plan

**Prepared for:** ROMTech Leadership **Subject:** Design and deployment of an internal, general-purpose AI assistant for ROMTech employees as an alternative to Microsoft Copilot, built on Azure AI Foundry endpoints, fronted by an open-source ChatGPT-style web application **Status:** Recommended plan and architecture

---

## 1. Executive Summary

ROMTech will deploy an internal, general-purpose AI chat assistant for employees as an alternative to Microsoft Copilot. The system will use Azure AI Foundry model endpoints under our existing BAA, with identity provided by Okta and access via a tile in the Okta dashboard. Engineering use cases (coding, architecture) are explicitly out of scope and continue to be served by Claude Code and the Claude API.

The recommendation is to **deploy LibreChat, an open-source ChatGPT-style web application, configured against our Azure Foundry endpoints**, with an LLM gateway (LiteLLM) between the application and the model layer for cost tracking, audit logging, DLP, and operational control. We will not build a custom chat UI.

This approach delivers a ChatGPT-equivalent experience to employees in weeks rather than quarters, places all conversation data inside our Azure tenant under our BAA, and converts the project from an ongoing application-development commitment into a bounded deployment-and-operations commitment.

The primary rationale: the open-source chat UI ecosystem has matured to the point where LibreChat and Open WebUI deliver ~90% of the ChatGPT user experience out of the box. The remaining 10% is not where ROMTech-specific value lives. Engineering time is better spent on integration, security, policy, RAG, and operations than on rebuilding chat-UI features that already exist and that we will then have to maintain forever in pace with ChatGPT's quarterly evolution.

---

## 2. Goals and Non-Goals

### Goals

- Provide ROMTech employees with a familiar, ChatGPT-style general-purpose AI assistant for everyday knowledge work: drafting, summarizing, analysis, research, translation, brainstorming, and similar tasks.
- Keep all conversation data, logs, and any indexed company documents inside ROMTech's Azure tenant under our existing BAA.
- Authenticate users via Okta SSO with an Okta dashboard tile launching the application.
- Provide administrative visibility into usage, cost, and compliance-relevant events.
- Reduce shadow-IT use of personal ChatGPT or Copilot accounts by offering an internal tool that is good enough that employees prefer it.

### Non-Goals

- Engineering coding and architecture work — these continue to be served by Claude Code and the Claude API.
- Customer-facing chatbot capability — this is internal only.
- Building a custom chat UI from scratch.
- Replacing Microsoft 365 productivity tools — this is a complement, not a replacement.
- Full enterprise knowledge search across all company systems at launch — this is a Phase 2 consideration.

---

## 3. Architecture

### 3.1 Logical Architecture

The system uses a four-layer pattern that has consolidated as the standard for internal AI chat deployments:

```
┌─────────────────────────────────────────────────────────────┐
│                     Employees                                │
│                  (Browser / Mobile)                          │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTPS
                              │
                    ┌─────────▼─────────┐
                    │   Okta SSO        │
                    │   (OIDC + SCIM)   │
                    └─────────┬─────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│           ROMTech Azure Tenant (BAA-eligible)               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Layer 1: Chat UI                                     │  │
│  │  LibreChat (App Service or AKS)                       │  │
│  │  - Streaming responses, conversation history          │  │
│  │  - File upload, image input, model picker             │  │
│  │  - Branded as ROMTech AI                              │  │
│  └────────────────────────┬─────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐  │
│  │  Layer 2: Application State                           │  │
│  │  - MongoDB (Cosmos DB) for conversation history       │  │
│  │  - Azure Blob Storage for uploaded files              │  │
│  │  - (Phase 2) Vector DB for RAG                        │  │
│  └────────────────────────┬─────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐  │
│  │  Layer 3: LLM Gateway                                 │  │
│  │  LiteLLM (containerized)                              │  │
│  │  - Virtual API keys per user/team                     │  │
│  │  - Cost tracking, rate limits, budget caps            │  │
│  │  - Audit logging, DLP hooks, content filters          │  │
│  │  - Multi-provider failover                            │  │
│  └────────────────────────┬─────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐  │
│  │  Layer 4: Models                                      │  │
│  │  Azure AI Foundry / Azure OpenAI                      │  │
│  │  - GPT-4-class model (general use)                    │  │
│  │  - GPT-4o-mini-class model (fast / cheap)             │  │
│  │  - (Optional) Image generation, embeddings            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Cross-cutting:                                              │
│  - Azure Key Vault (secrets)                                 │
│  - Azure Monitor / Log Analytics (observability)             │
│  - Azure Private Endpoints (network isolation)               │
│  - Microsoft Purview or equivalent (DLP, optional Phase 2)   │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Network and Identity Boundary

- The application is reachable only via the Okta tile, behind ROMTech's firewall or Azure Front Door with WAF rules limiting access to authenticated users on the corporate network or via VPN, depending on your standard pattern. (A Web Application Firewall (WAF) is a security layer in front of a web app that inspects incoming HTTP traffic and blocks malicious or unauthorized requests based on configurable rules — like blocking common attack patterns (SQL injection, XSS) or restricting access to specific IP ranges.)
- All Azure PaaS services communicate over private endpoints inside a dedicated VNet.
- All model traffic to Azure AI Foundry is private — it does not leave the Azure backbone.
- The LiteLLM gateway holds all model provider keys in Azure Key Vault; the LibreChat application never sees raw model keys.

### 3.3 Why This Pattern

Every layer in the diagram exists because removing it causes a known operational problem:

- **Without the gateway (Layer 3)**: cost is unattributable, budgets are unenforceable, every change in model strategy requires application code changes, audit logging has to be reimplemented in every callsite, and failover requires a deployment.
- **Without separate state storage (Layer 2)**: conversations are tied to a single application instance, which prevents horizontal scaling and complicates backup and retention.
- **Without the UI layer (Layer 1) as a separate, swappable component**: we'd be writing UI code, which is the situation we're explicitly avoiding.

---

## 4. Component Recommendations

### 4.1 Chat UI: LibreChat

**Recommendation:** LibreChat.

**Rationale:**

- Open-source (MIT license), self-hosted, designed specifically to be a ChatGPT-style internal corporate tool.
- First-class support for Azure OpenAI and any OpenAI-compatible custom endpoint, which covers our Foundry deployments.
- Strong enterprise authentication: OIDC (including Okta), OAuth, LDAP, SAML support via standard OIDC patterns.
- Conversation history persisted in MongoDB (which we will deploy as Cosmos DB with the MongoDB API for BAA coverage and managed operations).
- Familiar UI — visually and behaviorally close to ChatGPT, minimizing employee retraining.
- Active development, large community, GitHub-trending project.
- Acquired by ClickHouse in November 2025, which has been read by the community as a positive signal for continued investment, though we should monitor the roadmap.
- Supports advanced features that meet stated table-stakes requirements: streaming, file upload, image input, web search, code interpreter, in-chat artifact generation, MCP support, model picker, prompt presets, conversation forking.

**Alternative considered: Open WebUI.** Slightly more polished UX, larger user base (124K+ GitHub stars, 282M+ downloads), but its enterprise SSO and multi-provider story is somewhat thinner than LibreChat's and its architectural roots are in local-model (Ollama) deployments. Best suited to teams that lead with local models — not our situation.

**Alternative considered: Build custom.** Explicitly ruled out by ROMTech leadership. The rationale is sound: the engineering cost of building and then maintaining feature parity with ChatGPT is high and ongoing, and the value of doing so is low because chat-UI features are not a ROMTech differentiator.

### 4.2 LLM Gateway: LiteLLM

**Recommendation:** LiteLLM, self-hosted in our Azure tenant.

**Rationale:**

- Open-source, MIT-licensed, OpenAI-compatible proxy that routes to 100+ model providers including Azure OpenAI and Azure AI Foundry.
- Used in AWS's published reference architecture for multi-provider AI gateways, indicating maturity.
- Provides every gateway-layer capability we need without commercial licensing: virtual API keys per user/team/app, hierarchical budgets, hard spend caps, rate limiting, audit logs, content filter integration, multi-provider failover, semantic caching.
- Optional enterprise edition exists if we later want vendor support, SSO on the admin UI, and additional features — but the open-source version is production-ready.

**Alternatives considered:**

- **Portkey, Bifrost (commercial)**: more polished admin UIs and SSO out of the box, useful if our internal operations team prefers a vendor relationship over self-supported open source. Worth a look during the evaluation phase if LiteLLM's admin UI proves insufficient.
- **MLflow AI Gateway**: strong pure-OSS competitor, Apache 2.0, backed by Linux Foundation. Reasonable alternative if our team has existing MLflow operational expertise.
- **Databricks Unity AI Gateway**: only relevant if we're a Databricks shop.
- **No gateway at all**: not recommended. The cost of retrofitting the gateway later, once application code has been written to call Azure endpoints directly, is significantly higher than the cost of including it from day one. Even if we used only Azure OpenAI forever, the cost attribution, audit logging, and DLP integration benefits justify the gateway by themselves.

### 4.3 Model Layer: Azure AI Foundry / Azure OpenAI

**Recommendation:** Azure AI Foundry endpoints, with Azure OpenAI Service as the primary model source.

**Rationale:**

- Already established as the ROMTech path, with BAA coverage in place.
- Keeps all model traffic inside our Azure tenant via private endpoints.
- Existing Azure governance, compliance posture (SOC 2, HIPAA), and contractual relationship.
- Identity integrates with Entra ID for service-to-service auth between the gateway and Foundry.

**Model selection at launch:** Start with two models, expand based on usage.

- **One general-purpose flagship model** (GPT-4-class) — the default for most interactions.
- **One faster, cheaper model** (GPT-4o-mini-class) — for high-volume, low-complexity tasks; can be set as default for some teams or made user-selectable.
- **Optional, Phase 1.5:** image generation (DALL-E 3 via Azure OpenAI) and embeddings for RAG.

**Resist** the temptation to expose Foundry's full catalog at launch. Every model added is another BAA verification, another set of behavioral quirks for users to learn, another support surface for IT. Add new models based on demonstrated demand, not on theoretical optionality.

### 4.4 Identity: Okta

**Recommendation:** OIDC integration between LibreChat and Okta, with SCIM provisioning from Okta to LibreChat, and Okta groups driving authorization decisions.

**Specific configuration:**

- Create an OIDC application in Okta for "ROMTech AI."
- Configure LibreChat's `OPENID_*` environment variables to point to Okta's discovery endpoint.
- Map standard claims: `email`, `name`, and `groups`.
- Use Okta groups for feature gating: for example, an `ai-power-users` group might get access to image generation; a `ai-restricted` group (if needed for compliance reasons) might be limited to specific models.
- Implement SCIM so that deprovisioning in Okta automatically disables the user in LibreChat without manual IT intervention.
- The Okta tile launches the application's `/oauth/login` endpoint, which initiates the standard OIDC flow.

This is well-trodden ground. LibreChat's Okta integration is documented and used by many organizations.

### 4.5 Data Stores

- **Conversation history:** Cosmos DB with the MongoDB API, in a BAA-eligible region. LibreChat speaks MongoDB natively; Cosmos provides the managed-operations and HA story we want.
- **File uploads:** Azure Blob Storage with private endpoints and encryption at rest.
- **Vector store (Phase 2, when we add RAG):** Azure AI Search or pgvector on Azure Database for PostgreSQL — decide at the time based on document volume and access-control complexity.
- **Secrets:** Azure Key Vault, accessed via managed identities.
- **Observability:** Azure Monitor and Log Analytics; LiteLLM's audit logs can be forwarded here.

### 4.6 Deployment Platform

Two reasonable options:

- **Azure App Service** for the LibreChat container, with Container Apps or App Service for LiteLLM. Simpler operations, well-understood patterns, fine for our expected scale.
- **AKS (Azure Kubernetes Service)** if ROMTech has standardized on Kubernetes for internal applications. More operational overhead but more flexibility.

**Recommendation:** Azure Container Apps unless we already have an AKS operational practice. Container Apps gives us the container-based deployment model that LibreChat and LiteLLM both expect, with managed scaling and networking, and without the AKS operational tax.

---

## 5. Security, Compliance, and Privacy

### 5.1 BAA-Relevant Controls

- All components hosted in BAA-eligible Azure services within ROMTech's Azure tenant.
- All inter-service traffic over private endpoints; no model traffic transits the public internet.
- Encryption at rest (Azure-managed keys at minimum; customer-managed keys if our compliance posture requires it) for conversation history, uploaded files, and logs.
- Encryption in transit (TLS 1.2+) for all paths.
- Managed identities for service-to-service auth; no service account passwords stored anywhere.
- Audit logs retained per a written retention policy (recommended: 1 year minimum for audit logs, separate from conversation content retention).

### 5.2 Conversation Content Retention

The default — "keep conversations forever" — is convenient but creates a discovery liability and runs against the principle of data minimization. **Recommendation: 90 days for conversation content by default, with the ability for users to delete conversations earlier.** This is long enough to be useful (continuing a project across a few weeks) and short enough to bound legal exposure. This setting should be reviewed by Legal and Compliance before launch.

Metadata (user, model, token counts, timestamps — but not message content) can be retained longer for cost attribution and audit purposes.

### 5.3 DLP (Data Loss Prevention)

PHI may flow through this system. Even though everything is BAA-covered, we want to detect patterns where sensitive data is being used in inappropriate contexts (e.g., an employee pasting patient identifiers into a "rewrite this email" request).

**Recommendation:** Implement DLP at the LiteLLM gateway layer, either via LiteLLM's content filtering hooks, an Azure Content Safety integration, or Microsoft Purview if we already have it licensed. At launch, start with detection and logging rather than blocking — blocking based on false positives is the fastest way to drive employees back to personal ChatGPT. Move to blocking on specific high-confidence patterns once we've calibrated.

### 5.4 Content Moderation

Azure OpenAI includes content filtering by default. Keep it on. Add an internal review queue for flagged content so security or HR can investigate patterns over time.

### 5.5 System Prompt and Guardrails

Draft a short, clear system prompt that establishes:

- Identity: "You are ROMTech's internal AI assistant."
- Scope: general-purpose knowledge work; route specific kinds of questions (HR matters, legal questions, security incidents) to the appropriate internal channel.
- Constraints: do not generate content of [X categories] that ROMTech has determined is out of bounds.

The exact content of this prompt should be drafted by the project team and reviewed by Legal, HR, and Compliance.

### 5.6 Acceptable Use Policy

A short employee-facing AUP should be in place at launch covering: what the tool is and isn't for, that conversations are logged, retention policy, prohibition on entering specific data types if any, and where to report problems. This is standard for any new internal tool and should be reviewed by Legal and HR.

---

## 6. Operations and Cost Management

### 6.1 Cost Attribution

The LiteLLM gateway should issue virtual API keys per department or team, with metadata tags. This gives us monthly cost breakdowns by org unit, which is essential for budget planning and chargebacks if we ever want them. Without this, the Azure OpenAI bill is one undifferentiated number.

### 6.2 Budgets and Rate Limits

- Per-user soft daily token limits to prevent runaway use (a runaway script can rack up significant cost in hours).
- Per-team monthly hard caps with alerting at 75% and 90%.
- Global circuit breaker to disable the whole service if total spend in a 24-hour window exceeds a defined threshold — protects against catastrophic misconfiguration.

### 6.3 Observability

- Application Insights / Azure Monitor for LibreChat and LiteLLM telemetry.
- A dashboard covering: active users, conversations per day, tokens by model, cost by team, error rates, response latency, content-filter triggers, DLP triggers.
- Alerting on: service availability, cost anomalies, repeated authentication failures, security events.

### 6.4 Support Model

- Tier 1: IT helpdesk for access, login, and basic usage questions.
- Tier 2: the internal team that owns this service for application issues, model issues, integration issues.
- Documentation: an internal wiki page with FAQs, the AUP, model differences, "how to write good prompts" guidance, and known limitations.

### 6.5 Upgrade Cadence

LibreChat and LiteLLM both release frequently. **Recommended cadence:** test new versions in a staging environment monthly, promote to production quarterly unless there's a security fix that warrants faster movement. Pin specific versions in production; do not auto-update.

---

## 7. Phased Delivery

### Phase 0: Evaluation and Foundation (Weeks 1–2)

- Stand up LibreChat in a non-production Azure subscription with a sample Foundry endpoint.
- Validate: streaming behavior, file upload, conversation persistence, the specific Azure Foundry endpoint shapes we plan to use (Azure OpenAI, plus any non-OpenAI Foundry models if planned).
- Validate Okta OIDC integration end to end.
- Stand up LiteLLM in front and validate end-to-end traffic flow.
- Decision gate: does LibreChat meet our requirements? If specific gaps emerge, decide here whether they're showstoppers or acceptable.

### Phase 1: Pilot (Weeks 3–6)

- Production-quality deployment in our Azure tenant: VNet, private endpoints, Key Vault, Cosmos DB, App Service or Container Apps, monitoring.
- Okta integration with SCIM provisioning.
- LiteLLM gateway with cost attribution, basic rate limits, audit logging.
- Two models exposed: one flagship, one fast/cheap.
- Light branding (logo, name, colors).
- Pilot group: 20–50 users across a representative mix of departments.
- AUP, system prompt, support documentation in place.
- Run for 4 weeks. Collect: usage patterns, feature requests, problems, cost data.

### Phase 2: General Availability (Weeks 7–10)

- Incorporate pilot feedback.
- Tune rate limits and budgets based on observed pilot usage.
- Roll out to all employees via Okta group assignment, in tranches if our standard practice is staged rollouts.
- Communications plan: announcement, training session or recorded demo, documentation links.

### Phase 3: Enhanced Capability (Months 3–6)

Decide based on real usage data, not on theoretical demand:

- RAG over a curated set of internal documents (HR policies, IT documentation, employee handbook). This is the highest-value enhancement for most internal chat tools.
- Image generation if requested.
- Additional models added to the picker based on use cases that the flagship model handles poorly.
- Custom assistants / prompt templates for specific recurring tasks (e.g., a "meeting summarizer," a "policy lookup" assistant).
- Slack or Teams integration if there's demand and a clear use case.

### Phase 4 and beyond

- Permission-aware enterprise search across multiple internal systems (Confluence, SharePoint, Google Drive, etc.) is a significant additional project, not a configuration change. Treat as a separate initiative if it becomes a priority.

---

## 8. Risks and Mitigations

|Risk|Likelihood|Impact|Mitigation|
|---|---|---|---|
|Employees find the tool less polished than ChatGPT and route around it|Medium|High|Use LibreChat (which is very close to ChatGPT) rather than building; keep upgrade cadence current; collect feedback during pilot|
|Cost runs higher than budgeted|Medium|Medium|Hard per-team caps in LiteLLM; daily/weekly spend dashboards; global circuit breaker|
|Sensitive data is pasted into prompts inappropriately|High|Medium-High|DLP at the gateway (detect first, block later); AUP; user training; system prompt guidance|
|Azure Foundry endpoint behavior differs from documented OpenAI API in subtle ways|Low-Medium|Medium|Validate in Phase 0; maintain a test suite of representative prompts; pin model versions|
|LibreChat project direction changes post-ClickHouse acquisition in ways that affect us|Low-Medium|Medium|Monitor roadmap quarterly; the application is open source and we can fork if necessary; LiteLLM gateway means the model layer is portable regardless|
|BAA scope confusion — a specific Foundry-catalog model gets enabled that isn't BAA-covered|Medium|High|Explicit allowlist of models in LiteLLM; gateway rejects any model not on the list; quarterly BAA-coverage review for enabled models|
|Audit/discovery request for conversation contents|Medium|Medium|Documented retention policy, audit logs, conversation deletion capability; Legal sign-off before launch|
|User identity claims from Okta don't carry the attributes we need for feature gating|Low|Low|Validated in Phase 0|

---

## 9. Effort and Cost (Rough Order of Magnitude)

**Engineering effort:** Two to three engineers part-time, or one to two full-time, over roughly 8–10 weeks to reach GA. The work is roughly 70% Azure infrastructure, networking, and identity integration, 20% configuration and policy, and 10% light theming and documentation. Substantially less than a custom build, which would be measured in quarters with a larger team.

**Ongoing operations:** One engineer at perhaps 25–40% allocation for steady-state, more during quarterly upgrades and feature additions. This is real and worth budgeting honestly.

**Run cost (Azure infrastructure, excluding model token costs):** Modest — App Service or Container Apps, Cosmos DB, supporting services. Likely a few hundred to low thousands of dollars per month depending on scale and HA configuration.

**Run cost (model tokens):** This is the dominant variable cost and depends entirely on usage. A reasonable planning assumption for a general-purpose internal chatbot is in the low single-digit dollars per active user per month on average, with heavy users at 5–10x that. Real numbers will emerge from the pilot. The LiteLLM gateway makes these costs visible and controllable.

---

## 10. Recommended Decisions and Next Steps

The following decisions should be made before Phase 0 begins. I've noted my recommendation in each case.

1. **Chat UI:** LibreChat. _Recommended._
2. **Gateway:** LiteLLM (open-source, self-hosted). _Recommended._
3. **Deployment platform:** Azure Container Apps unless ROMTech has standardized on AKS. _Recommended._
4. **Model strategy at launch:** Two models (flagship + fast/cheap), Azure OpenAI primary, all enabled models verified BAA-eligible. _Recommended._
5. **Conversation retention:** 90 days default, user-deletable earlier, separate longer retention for metadata. Requires Legal/Compliance review. _Recommended starting point._
6. **DLP approach:** Detect-and-log at launch via gateway; move to blocking specific high-confidence patterns later. _Recommended._
7. **Pilot group size and composition:** 20–50 users across a representative departmental mix. _Recommended._
8. **Phase 2 RAG:** Defer to Phase 3, target a curated initial document set (HR policies, IT docs) rather than enterprise-wide search. _Recommended._

### Immediate next steps

1. Confirm this plan with the AI Team Lead and reconcile against the original Teams message — specifically the "build it ourselves" framing.
2. Identify a project owner and the small engineering team for Phase 0.
3. Identify the Legal/Compliance reviewer for retention policy and AUP.
4. Schedule a Phase 0 kickoff to validate the technical assumptions before further commitment.
5. Open conversation with Azure team on the specific Foundry deployment configuration (regions, model availability, BAA scope).

---

## 11. Key Assumptions

I want to make these explicit so they can be challenged:

- **ROMTech has an existing Azure tenant** with a sufficient governance footprint (subscriptions, networking, identity, monitoring) that this project can be deployed inside it without building foundational infrastructure first.
- **Okta is the production identity provider** and supports OIDC application creation and SCIM provisioning per ROMTech's standard pattern.
- **The BAA path through Azure AI Foundry is already established** by the AI Team Lead's earlier work; this plan assumes that path is real and available.
- **Engineering scope is not a blocker** — meaning two or three part-time engineers can be allocated for ~10 weeks. If the available engineering capacity is materially smaller than that, the timeline lengthens.
- **The pilot group can be recruited** from departments willing to provide structured feedback during weeks 3–6.
- **Microsoft Copilot is not being eliminated** — this is an alternative for use cases where Copilot doesn't fit, not necessarily a replacement. If full replacement is the goal, that's a different conversation with different licensing implications.

