# Security Policy

## Supported releases

Security fixes are applied to the current default branch and the latest published release once releases are established.

## Reporting a vulnerability

Please do **not** disclose vulnerabilities, credentials, private documents, or proof-of-concept exploit details in a public issue, discussion, pull request, or screenshot.

Before accepting public contributions, the maintainer should enable GitHub private vulnerability reporting for this repository and publish a maintained private security contact in the repository settings. Until then, contact the maintainer through an existing private channel and include:

- a concise description of the impact;
- affected component and version/commit;
- reproducible steps or a minimal proof of concept;
- any suggested mitigation;
- a safe way to acknowledge receipt.

## Sensitive data rules

- Never commit `backend/.env`, `.env.prod`, API keys, passwords, deploy keys, database dumps, tokens, or production logs.
- Treat uploaded source material and generated project media as potentially sensitive.
- Do not expose server filesystem paths or provider-signed URLs in generated HTML or exports.
- Rotate a credential immediately if it is ever committed, pasted to an issue, or otherwise disclosed; deleting the line alone does not revoke it.

## Scope notes

This application can execute model-produced HTML in an isolated report preview and supports configurable model/image/storage providers. Security reviews should pay particular attention to HTML sanitisation, export bundling, media validation, authentication, access control, dependency updates, and secret handling.
