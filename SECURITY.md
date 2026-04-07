# Security Policy

## Reporting Vulnerabilities

If you discover a security issue, please report it via GitHub Security Advisories (private).

**Do NOT:**

- Open public issues for security vulnerabilities
- Include sensitive data in experiment logs
- Commit credentials or API keys

## What to Report

- Infrastructure vulnerabilities in provided scripts
- Sensitive data exposure in documentation
- Security issues in sample code

## Response Timeline

- Acknowledgment: 48 hours
- Initial assessment: 7 days
- Resolution: Depends on severity

## Security Best Practices for Contributors

When contributing experiments or scripts:

1. Never hardcode credentials or API keys
2. Use environment variables for sensitive values
3. Sanitize any logs or output before committing
4. Review scripts for command injection vulnerabilities
