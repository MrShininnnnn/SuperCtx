# Security Policy

## Supported Versions

SuperCtx is currently pre-1.0. Security fixes are handled on the default branch and included in the next release.

| Version | Supported |
| ------- | --------- |
| `main`  | Yes       |
| `<0.1`  | No        |

## Reporting a Vulnerability

Do not open a public GitHub issue for suspected vulnerabilities.

Use GitHub's private vulnerability reporting flow if it is available for this repository:

```text
https://github.com/MrShininnnnn/SuperCtx/security/advisories/new
```

If private reporting is unavailable, email the maintainer at `mrshininnnnn@gmail.com` before sharing exploit details in public.

Please include:

- affected version or commit
- operating system and Python version
- steps to reproduce
- expected impact
- any safe proof-of-concept details

## Security Expectations

SuperCtx is designed to keep context project-local. Do not sync secrets, credentials, API keys, tokens, cache files, or private session data into `.ctx/`.

Security reports will be reviewed as soon as practical. Confirmed vulnerabilities will be fixed on the default branch before public disclosure details are added.
