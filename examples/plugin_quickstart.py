"""Provider-independent SELFGuard plug-in example."""

from selfguard import PromptBlockedError, PromptInjectionPlugin, PromptReviewRequired


plugin = PromptInjectionPlugin.from_bundle(
    "selfguard_prompt_plugin.sgplugin",
    expected_sha256="replace-with-the-published-bundle-sha256",
)


def generate(prompt: str) -> str:
    """Replace this with the intended provider call."""

    return f"model response for: {prompt}"


safe_generate = plugin.wrap(generate)

try:
    print(safe_generate("Where is my order?"))
except PromptReviewRequired as exc:
    print("Send to trusted review:", exc.decision.decision_id)
except PromptBlockedError as exc:
    print("Blocked:", exc.decision.reason_code)
