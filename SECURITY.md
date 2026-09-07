# Security Policy

## Supported Security Work

OwnSIS is in its first working-release phase. Until a tagged supported-version
policy is published, security fixes are made on the current `main` branch. No
commit in this repository should be interpreted as a production certification.

## Report a Vulnerability Privately

Do not disclose suspected vulnerabilities, exploit details, credentials,
personal data, or tenant information in a public issue, pull request, commit, or
discussion.

Use the repository's private GitHub security-advisory form:
[report a vulnerability privately](https://github.com/oneku16/onwlms/security/advisories/new).
If GitHub does not present that form to you, open a public issue containing only
the sentence “Please provide a private security contact.” Do not include any
technical detail in that issue.

Include in the private report, when safe:

- affected revision and deployment topology;
- the tenant/identity boundary involved, using synthetic identifiers;
- reproducible steps with secrets and personal data removed;
- observed and potential impact;
- whether exploitation is ongoing or public; and
- a safe way for maintainers to request more information.

Maintainers must acknowledge the private report, assign a confidential owner,
preserve evidence, assess tenant impact, and coordinate remediation and
disclosure. Exact response-time commitments will be published only after the
maintainer rotation and service objectives are approved.

## Security Priorities

Cross-tenant exposure, authentication or authorization bypass, official-record
integrity loss, session or provider-token disclosure, remote code execution,
destructive data loss, and supply-chain compromise receive immediate containment
priority. Do not test a suspected issue against production or another
organization's data without explicit written authorization.
