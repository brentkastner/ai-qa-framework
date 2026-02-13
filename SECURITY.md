# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do not open a public issue for security vulnerabilities.**

Instead, please use one of the following methods:

1. **GitHub Security Advisories (preferred):** Report via [GitHub Security Advisories](https://github.com/brentkastner/ai-qa-framework/security/advisories/new)
2. **Email:** Contact the maintainer directly at the email listed on the [GitHub profile](https://github.com/brentkastner)

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix or mitigation:** Depends on severity, but we aim for prompt resolution

## Scope

The following are in scope for security reports:

- Vulnerabilities in the framework's source code
- Issues with how credentials or API keys are handled
- Security problems in generated test reports (e.g., XSS in HTML reports)
- Dependency vulnerabilities that directly affect this project

The following are **out of scope**:

- Vulnerabilities in websites being tested by the framework
- Issues in third-party dependencies that don't affect this project
- Social engineering attacks

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | Yes                |

## Security Best Practices for Users

- Never commit your `qa-config.json` file (it's in `.gitignore` by default)
- Use environment variables (`env:VAR_NAME`) for passwords and API keys
- Review HTML reports before sharing, as they may contain screenshots of authenticated pages
