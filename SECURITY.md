# Security Policy

## Research-preview status

SELFGuard v0.1 is experimental post-generation monitoring software. It does not make an LLM, agent, tool, or application secure by itself, and a non-flagged response must not be treated as trusted or authorized.

Only the latest `main` branch and the most recent tagged v0.1 release, if one exists, receive fixes. Older snapshots may be used for research reproduction but are not supported security boundaries.

## Reporting a vulnerability

Use a private GitHub Security Advisory for this repository if private reporting is enabled. If it is not available, open a minimal issue asking the maintainers to provide a private reporting channel. Do not include exploit details, secrets, private prompts, model outputs, credentials, or personal data in a public issue.

Include, when safe:

- affected version or commit;
- a concise impact description;
- the smallest reproducible example;
- required configuration and dependency versions; and
- suggested mitigations, if known.

Allow maintainers time to reproduce and coordinate a fix before public disclosure. No response-time or bounty commitment is made in this research preview.

Ordinary detector misses, false alarms, benchmark disagreements, and requests for new attack coverage are valuable research bug reports but are not necessarily software vulnerabilities. Credential exposure, unintended telemetry, dependency compromise, code execution, sandbox escape, or a bypass of an explicitly documented security boundary should be reported privately.

## Deployment guidance

- Run model and tool execution with least privilege, sandboxing, network restrictions, allowlists, validation, and explicit approval for consequential actions.
- Apply controls before tools execute. SELFGuard scores are computed after response generation, so display suppression cannot reverse generation-time side effects.
- Treat all model text, logs, serialized artifacts, and calibration input as untrusted.
- Do not deserialize untrusted `joblib`/pickle model artifacts; those formats can execute code while loading.
- Store API keys in a secret manager or environment variables, never in notebooks, examples, checkpoints, or commits.
- Pin and review dependencies and model revisions for production-like experiments.
- Recalibrate and validate thresholds for the intended model, prompt, language, domain, and attack prevalence.

## Telemetry and privacy

Telemetry is disabled by default and sends nothing unless the caller both opts in and configures an endpoint. When enabled, the JSON payload excludes prompts, user messages, response text, and direct identifiers, but includes random session IDs, timestamps, signal scores, outcomes, model type, threshold, and latency. Endpoint and network operators may still observe normal network metadata such as IP addresses and timing.

Review the endpoint, retention, access controls, legal basis, and user notice before enabling telemetry. Never configure an endpoint you do not control or trust.
