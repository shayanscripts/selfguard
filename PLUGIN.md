# Prompt-injection plug-in integration

`PromptInjectionPlugin` is a provider-independent pre-generation risk gate. It
inspects a prompt before invoking the wrapped LLM callable and produces three
states: allow, require review, or block.

It is not an authorization system. An allowed prompt may still yield unsafe or
incorrect output, and an adaptive injection may evade the model. Keep tools and
credentials behind `ActionBoundary`, least-privilege scopes, argument schemas,
sandboxing, rate limits, and approval for side effects.

## Install

```bash
python -m pip install "selfguard[plugin]"
```

## Load a verified model bundle

Never load a model from an untrusted pickle or joblib file. SELFGuard plug-in
bundles use `skops`, exact member coverage, a per-member SHA-256 manifest, and
an optional expected outer-bundle hash.

```python
from selfguard import PromptInjectionPlugin

plugin = PromptInjectionPlugin.from_bundle(
    "selfguard_prompt_plugin.sgplugin",
    expected_sha256="<sha256 supplied with the release>",
)
```

The v5 notebook exports a development candidate. Do not remove its development
status or distribute it as production-ready until a sealed promotion test has
passed.

## Wrap any Python LLM callable

```python
def call_model(prompt: str) -> str:
    return provider.generate(prompt)

safe_call_model = plugin.wrap(call_model)
result = safe_call_model("Where is my order?")
```

Blocked prompts raise `PromptBlockedError`. Scores in the review band raise
`PromptReviewRequired`; route these to a trusted review workflow rather than
silently allowing them.

For APIs whose prompt is not the first positional parameter, provide a trusted
extractor:

```python
def extract_responses_input(args, kwargs):
    value = kwargs["input"]
    if not isinstance(value, str):
        raise TypeError("this integration accepts string input only")
    return value

safe_create = plugin.wrap(
    client.responses.create,
    prompt_extractor=extract_responses_input,
)
response = safe_create(model="your-model", input="Where is my order?")
```

The extractor is security-sensitive application code. It must include every
untrusted text channel: user input, retrieved documents, tool results, web-page
content, file contents, and prior untrusted messages. Inspecting only the last
user message does not defend against indirect prompt injection.

## Privacy-conscious audit events

Provide an `audit_sink` to receive the decision, numeric score, prompt length,
and SHA-256 digest. Raw prompt text is not included. Audit failures are
fail-closed by default.

```python
plugin = PromptInjectionPlugin.from_bundle(
    "selfguard_prompt_plugin.sgplugin",
    expected_sha256="<release hash>",
    audit_sink=write_security_event,
)
```

Hashing does not anonymize low-entropy prompts. Treat audit data as sensitive,
apply access control and retention limits, and consider an application-secret
HMAC if offline guessing is a concern.
