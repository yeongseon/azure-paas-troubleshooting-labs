# AGENTS.md

Guidance for AI agents working in this repository.

## Project Overview

**Azure PaaS Troubleshooting Labs** — Support-engineer-style troubleshooting experiments for Azure App Service, Azure Functions, and Azure Container Apps.

- **Live site**: https://yeongseon.github.io/azure-paas-troubleshooting-labs/
- **Repository**: https://github.com/yeongseon/azure-paas-troubleshooting-labs

## Repository Structure

```
azure-paas-troubleshooting-labs/
├── docs/                          # MkDocs documentation source
│   ├── index.md                   # Home page
│   ├── about.md                   # About this project
│   ├── methodology/               # Experiment framework, evidence levels
│   ├── app-service/               # App Service experiments
│   ├── functions/                 # Azure Functions experiments
│   ├── container-apps/            # Container Apps experiments
│   └── patterns/                  # Cross-cutting patterns
├── experiments/                   # Reproduction assets
│   ├── templates/                 # Canonical experiment template
│   ├── app-service/               # App Service reproduction scripts
│   ├── functions/                 # Functions reproduction scripts
│   └── container-apps/            # Container Apps reproduction scripts
├── .github/workflows/             # CI/CD workflows
├── mkdocs.yml                     # MkDocs configuration
└── README.md                      # Repository overview
```

## Content Types

### Experiments (Primary Content)

- Location: `docs/{service}/{experiment}/overview.md`
- Template: `experiments/templates/experiment-template.md`
- Structure: 16 sections (Question → Support Takeaway)

### Methodology

- Location: `docs/methodology/`
- Defines evidence levels, interpretation guidelines

### Patterns

- Location: `docs/patterns/`
- Cross-cutting troubleshooting patterns

## Documentation Conventions

### Experiment Status

```markdown
!!! info "Status: Published"
    Experiment completed with real data

!!! info "Status: Draft - Awaiting Execution"
    Designed but not executed

!!! info "Status: Planned"
    Outline only
```

### Evidence Level Tags

Always use calibrated tags in interpretations:

- **Observed**: Directly seen in logs/metrics
- **Measured**: Quantitatively confirmed
- **Correlated**: Signals moved together
- **Inferred**: Reasonable conclusion
- **Strongly Suggested**: Strong but not definitive
- **Not Proven**: Tested but not confirmed
- **Unknown**: Insufficient data

### Admonition Style

```markdown
!!! warning "Important"
    Content indented 4 spaces.
```

### Code Blocks

- Always include language identifier
- Use `bash` for shell commands
- Use `python` for Python code
- Use `kusto` for KQL queries

## Build and Preview

```bash
make install  # Install dependencies
make serve    # Local preview at localhost:8000
make build    # Build with strict validation
```

## Git Commit Style

```
type: short description
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`

## Quality Gates

Before committing:

1. `mkdocs build --strict` must pass
2. All experiments must follow 16-section template
3. Evidence tags must be used for conclusions
4. No placeholder sections in "Published" experiments
