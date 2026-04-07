# About This Project

## Background

Azure PaaS services — App Service, Functions, Container Apps — are well-documented on Microsoft Learn. The official documentation is accurate and comprehensive for standard usage patterns.

However, real-world support and troubleshooting scenarios frequently encounter situations that official documentation does not address:

- Edge cases that only surface under specific load, timing, or configuration conditions
- Ambiguity about whether an observed behavior is a platform issue or an application issue
- Metrics and signals that are technically correct but easily misinterpreted
- Gaps between what can be stated with confidence and what requires additional evidence

This repository exists to fill those gaps through reproducible, evidence-based experiments.

## Goals

- Reproduce Azure PaaS edge cases and failure modes through controlled experiments
- Standardize the experiment structure: question, hypothesis, observation, interpretation, limits
- Build a reusable troubleshooting knowledge base grounded in evidence, not assumption
- Serve as a deeper evidence layer that complements the practical guide series
- Provide support-ready interpretations that distinguish between observed facts and inferences

## Non-goals

- This is not a beginner's guide to Azure PaaS services
- This is not a replacement for Microsoft Learn documentation
- This is not an exhaustive performance benchmark suite
- This is not an official RCA or Microsoft internal analysis
- This does not attempt to reproduce every scenario in a production-identical environment

## Core principles

**Hypothesis-driven** — Every experiment starts with a clear question or testable prediction. No experiment is conducted "just to see what happens."

**Evidence over assertion** — Observed facts and interpretations are separated. Conclusions state their confidence level explicitly.

**Reproducibility** — Environment, conditions, and procedures are recorded in enough detail for others to repeat the experiment.

**Support-oriented interpretation** — Results are framed in terms of what a support engineer would need to know when handling a similar case.

**Platform/app boundary awareness** — Every experiment considers whether the observed behavior is platform-side, application-side, or a shared-resource effect.

**Clear limits** — Every experiment states what it does not prove. Over-claiming is treated as a defect.

## Target audience

**Primary:**

- Azure Support Engineers and Escalation Engineers
- Cloud platform operators running App Service, Functions, or Container Apps
- Engineers who need to distinguish platform issues from application issues

**Secondary:**

- SRE and platform engineering teams
- Developers building on Azure PaaS who want deeper understanding
- Technical writers and bloggers covering Azure troubleshooting

## Relationship with practical guides

This repository and the practical guide series serve different purposes:

| | Practical Guides | Troubleshooting Labs |
|---|---|---|
| **Scope** | Broad reference and operational guidance | Narrow, deep investigation |
| **Content** | Architecture, deployment, best practices | Failure reproduction, edge cases, evidence |
| **Tone** | Instructional | Investigative |
| **Evidence level** | Summarizes official guidance | Generates original experimental evidence |

The two are complementary. Lab experiments link to relevant guide sections for context; guides link to labs for deeper evidence.

## Author

By Yeongseon Choe

- GitHub: [github.com/yeongseon](https://github.com/yeongseon)
