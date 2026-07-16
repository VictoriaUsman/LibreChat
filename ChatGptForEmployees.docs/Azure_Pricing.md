Here is a highly structured, professionally formatted Markdown document of the Azure AI Model pricing data.

It has been optimized for visual clarity inside Git repositories (such as GitHub, GitLab, or Azure DevOps) by converting the raw nested text into clean Markdown tables with consistent unit formats, clear headers, and intuitive layouts.

```markdown
# Azure AI Model Pricing Reference Guide

A comprehensive pricing sheet for Azure AI Models. All listed prices are calculated **per 1 Million (1M) Tokens** unless specified otherwise.

---

## Table of Contents
1. [GPT-Chat Latest](#gpt-chat-latest)
2. [GPT 5.5 Series](#gpt-55-series)
3. [GPT 5.4 Series](#gpt-54-series)
4. [GPT 5.3 Series](#gpt-53-series)
5. [GPT 5.2 Series](#gpt-52-series)
6. [GPT 5.1 Series](#gpt-51-series)
7. [GPT-5 Series](#gpt-5-series-1)
8. [Deep Research](#deep-research)
9. [o3 Series](#o3-series)
10. [o4-mini Series](#o4-mini-series)
11. [GPT-4.1 Series](#gpt-41-series)

---

## GPT-Chat Latest

| Model | Pricing Type | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-Chat Latest 05052026 Global** | Standard | $5.00 | $0.50 | $30.00 |

---

## GPT 5.5 Series
*GPT-5.5 delivers advanced reasoning, instruction following, and agentic capabilities for production AI workloads.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-5.5 Global** | Standard | $5.00 | $0.50 | $30.00 |
| | Priority Processing | $12.50 | $1.25 | $75.00 |
| **GPT-5.5 Data Zone** | Standard | $5.50 | $0.55 | $33.00 |
| | Priority Processing | $13.75 | $1.38 | $82.50 |
| **GPT-5.5 Long Context Global** | Standard | $10.00 | $1.00 | $45.00 |
| | Priority Processing | — | — | — |
| **GPT-5.5 Long Context Data Zone**| Standard | $11.00 | $1.10 | $49.50 |
| | Priority Processing | — | — | — |

---

## GPT 5.4 Series
*Built for Reliable AI Production: Stronger reasoning, dependable execution, and agentic workflows at scale.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-5.4 (<272k context) Global** | Standard | $2.50 | $0.25 | $15.00 |
| | Priority Processing | $5.00 | $0.50 | $30.00 |
| | Batch API | $1.25 | $0.13 | $7.50 |
| **GPT-5.4 (<272k context) Data Zone**| Standard | $2.75 | $0.28 | $16.50 |
| | Priority Processing | $5.50 | $0.55 | $33.00 |
| | Batch API | — | — | — |
| **GPT-5.4 (>272k context) Global** | Standard | $5.00 | $0.50 | $22.50 |
| **GPT-5.4 Pro (<272k context) Global**| Standard | $30.00 | — | $180.00 |
| **GPT-5.4 Pro (>272k context) Global**| Standard | $60.00 | — | $270.00 |
| **GPT-5.4 mini Global** | Standard | $0.75 | $0.08 | $4.50 |
| | Priority Processing | $1.50 | $0.15 | $9.00 |
| **GPT-5.4 nano Global** | Standard | $0.20 | $0.02 | $1.25 |

---

## GPT 5.3 Series
*Unifies the frontier coding performance of GPT-5.2-Codex with the reasoning and professional knowledge capabilities of GPT-5.2.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-5.3 Codex Global** | Standard | $1.75 | $0.18 | $14.00 |
| | Priority Processing | $3.50 | $0.35 | $28.00 |
| **GPT-5.3 Chat Global** | Standard | $1.75 | $0.18 | $14.00 |

---

## GPT 5.2 Series
*GPT-5.2 delivers the deep reasoning and expanded context handling necessary for building sophisticated AI agents capable of automating complex, long-running tasks.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-5.2 Codex Global** | Standard | $1.75 | $0.18 | $14.00 |
| **GPT-5.2 Global** | Standard | $1.75 | $0.18 | $14.00 |
| | Priority Processing | $3.50 | $0.35 | $28.00 |
| **GPT-5.2 Data Zone** | Standard | $1.93 | $0.20 | $15.40 |
| | Priority Processing | $3.85 | $0.39 | $30.80 |
| **GPT-5.2-chat latest Global** | Standard | $1.75 | $0.18 | $14.00 |
| **GPT-5.2-chat Data Zone** | Standard | $1.93 | $0.20 | $15.40 |

---

## GPT 5.1 Series
*Built to respond faster with adaptive reasoning, improving latency and cost efficiency by dynamically adjusting thinking time.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-5.1 Global** | Standard | $1.25 | $0.13 | $10.00 |
| | Priority Processing | $2.50 | $0.25 | $20.00 |
| **GPT-5.1 Data Zone** | Standard | $1.38 | $0.14 | $11.00 |
| | Priority Processing | $2.75 | $0.28 | $22.00 |
| **GPT-5.1-chat Global** | Standard | $1.25 | $0.13 | $10.00 |
| **GPT-5.1-codex Global** | Standard | $1.25 | $0.13 | $10.00 |
| **GPT-5.1-codex-max Global** | Standard | $1.25 | $0.13 | $10.00 |
| **GPT-5.1-codex-mini Global** | Standard | $0.25 | $0.03 | $2.00 |

---

## GPT-5 Series
*Baseline GPT-5 models delivering highly capable core workflows.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-5 2025-08-07 Global** | Standard | $1.25 | $0.13 | $10.00 |
| | Priority Processing | $2.50 | $0.25 | $20.00 |
| | Batch API | $0.63 | $0.07 | $5.00 |
| **GPT-5 Data Zone** | Standard | $1.38 | $0.14 | $11.00 |
| | Priority Processing | $1.38 | $0.14 | $11.00 |
| | Batch API | $0.69 | $0.07 | $5.50 |
| **GPT-5 Pro Global** | Standard | $15.00 | — | $120.00 |
| **GPT-5 Codex Global** | Standard | $1.25 | $0.13 | $10.00 |
| **GPT-5-mini Global** | Standard | $0.25 | $0.03 | $2.00 |
| | Priority Processing | $0.45 | $0.05 | $3.60 |
| **GPT-5-mini Data Zone** | Standard | $0.28 | $0.03 | $2.20 |
| | Priority Processing | $0.50 | $0.05 | $3.96 |
| **GPT-5-nano Global** | Standard | $0.05 | $0.01 | $0.40 |
| **GPT-5-nano Data Zone** | Standard | $0.06 | $0.01 | $0.44 |
| **GPT-5 chat Global** | Standard | $1.25 | $0.13 | $10.00 |

---

## Deep Research
*Automates complex research tasks with structured, citation-rich answers grounded in real-time search data.*

* **Search Context Tokens:** Charged at the standard input token prices of the baseline model utilized.
* **Additional Fees:** Grounding with Bing Search and clarifying questions processed by the base GPT model will incur their respective individual charges.

| Model | Pricing Type | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **o3-deep research Global** | Standard | $10.00 | $2.50 | $40.00 |

---

## o3 Series
*A powerful reasoning model pushing frontiers in coding, science, mathematics, and visual perception. Has a 200k context window and a June 2024 knowledge cutoff.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **o3 2025-04-16 Global** | Standard | $2.00 | $0.50 | $8.00 |
| | Batch API | $1.00 | — | $4.00 |
| **o3 2025-04-16 Data Zone** | Standard | $2.20 | $0.55 | $8.80 |
| | Batch API | $1.10 | — | $4.40 |
| **o3 2025-04-16 Regional** | Standard | $2.20 | $0.55 | $8.80 |

---

## o4-mini Series
*Compact, highly efficient, and cost-effective reasoning model. Features a 200k context window and a June 2024 knowledge cutoff.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **o4-mini 2025-04-16 Global** | Standard | $1.10 | $0.28 | $4.40 |
| | Batch API | $0.55 | — | $2.20 |
| **o4-mini 2025-04-16 Data Zone** | Standard | $1.21 | $0.31 | $4.84 |
| | Batch API | $0.61 | — | $2.42 |
| **o4-mini 2025-04-16 Regional** | Standard | $1.21 | $0.31 | $4.84 |

---

## GPT-4.1 Series
*Highly advanced general-purpose model with extensive world knowledge. Features a 1M context window and a June 2024 knowledge cutoff.*

| Model | Tier / Processing | Input (per 1M) | Cached Input (per 1M) | Output (per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| **GPT-4.1-2025-04-14 Global** | Standard | $2.00 | $0.50 | $8.00 |
| | Priority Processing | $3.50 | $0.88 | $14.00 |
| | Batch API | $1.00 | — | $4.00 |
| **GPT-4.1-2025-04-14 Data Zone**| Standard | $2.20 | $0.55 | $8.80 |
| | Priority Processing | $3.85 | $0.97 | $15.40 |
| | Batch API | $1.10 | — | $4.40 |
| **GPT-4.1-2025-04-14 Regional** | Standard | $2.20 | $0.55 | $8.80 |
| **GPT-4.1-mini-2025-04-14 Global**| Standard | $0.40 | $0.10 | $1.60 |
| | Priority Processing | $0.70 | $0.18 | $2.80 |
| | Batch API | $0.20 | — | $0.80 |
| **GPT-4.1-mini-2025-04-14 Data Zone**| Standard | $0.44 | $0.11 | $1.76 |
| | Priority Processing | $0.77 | $0.20 | $3.08 |
| | Batch API | $0.22 | — | $0.88 |
| **GPT-4.1-mini-2025-04-14 Regional**| Standard | $0.44 | $0.11 | $1.76 |
| **GPT-4.1-nano-2025-04-14 Global**| Standard | $0.10 | $0.03 | $0.40 |
| | Batch API | $0.05 | — | $0.20 |
| **GPT-4.1-nano-2025-04-14 Data Zone**| Standard | $0.11 | $0.03 | $0.44 |
| | Batch API | $0.06 | — | $0.22 |
| **GPT-4.1-nano-2025-04-14 Regional**| Standard | $0.11 | $0.03 | $0.44 |

```