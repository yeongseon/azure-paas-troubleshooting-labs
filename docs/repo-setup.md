# Repository Setup Checklist

This document tracks repository configuration tasks.

## GitHub Repository Settings

### About Section
- **Description**: Support-engineer-style troubleshooting experiments for Azure App Service, Azure Functions, and Azure Container Apps
- **Website**: https://yeongseon.github.io/azure-paas-troubleshooting-labs/
- **Topics**: 
  - azure
  - azure-app-service
  - azure-functions
  - azure-container-apps
  - troubleshooting
  - devops
  - cloud
  - experiments
  - support-engineering

### Configuration Commands (for maintainer)

```bash
# Set description and homepage
gh repo edit yeongseon/azure-paas-troubleshooting-labs \
  --description "Support-engineer-style troubleshooting experiments for Azure App Service, Azure Functions, and Azure Container Apps" \
  --homepage "https://yeongseon.github.io/azure-paas-troubleshooting-labs/"

# Add topics
gh repo edit yeongseon/azure-paas-troubleshooting-labs \
  --add-topic azure \
  --add-topic azure-app-service \
  --add-topic azure-functions \
  --add-topic azure-container-apps \
  --add-topic troubleshooting \
  --add-topic devops \
  --add-topic cloud \
  --add-topic experiments
```

### GitHub Pages
- Source: GitHub Actions
- Custom domain: (none)
- Enforce HTTPS: Yes

### Branch Protection (main)
- Require pull request reviews: Recommended
- Require status checks: CI workflow

## Status
- [ ] Description set
- [ ] Homepage URL set  
- [ ] Topics added
- [ ] GitHub Pages enabled
- [ ] Branch protection configured
