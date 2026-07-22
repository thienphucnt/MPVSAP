# Security Policy

## Overview
MPVSAP is a fully automated video generation and publishing pipeline. Because this repository operates in a public environment with GitHub Actions workflows, security and credential isolation are top priorities.

## Security Controls & Guardrails
- **Credential Protection**: All API credentials (`GEMINI_API_KEY`, `PEXELS_API_KEY`, `YOUTUBE_CLIENT_SECRET`, etc.) are passed exclusively through encrypted **GitHub Repository Secrets**. Secrets are never logged or committed.
- **Workflow Execution Guardrails**: Autonomous issue bot triggers in `.github/workflows/antigravity_bot.yml` are restricted to repository owners (`author_association == 'OWNER'`). Public pull requests or issue comments from untrusted users cannot trigger GHA execution or access repository secrets.
- **Input Sanitization**: Search keywords passed to external media APIs (Pexels, Wikimedia Commons) are sanitized against special character injection.
- **Content Integrity**: All LLM-generated scripts undergo Pass 2 Auto-QA scoring and a Python `is_duplicate_topic` post-generation validator before video rendering or publishing.

## Reporting Vulnerabilities
If you discover a potential security vulnerability or secret leakage risk in this project, please **do not open a public issue**. Instead, report it directly to the repository maintainers.
