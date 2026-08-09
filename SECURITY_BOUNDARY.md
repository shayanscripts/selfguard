# Pre-action security boundary

`ActionBoundary` is a deny-by-default enforcement primitive for applications
that let an LLM propose tool calls. It is intentionally separate from response
generation: the planner must not possess executable tools. Proposed actions are
checked and only then dispatched to a registered handler.

SELFGuard remains one risk signal. A clean score can never grant access.

## Trust model

The following values must be supplied by trusted application code, not copied
from model output:

- the authenticated `principal_id`;
- `granted_scopes` from the application's authorization system;
- the registered `ToolPolicy` and handler;
- the approval verifier and approval token; and
- detector results produced by the configured guard.

Only `tool_name` and `arguments` are ordinarily derived from the model's typed
plan. The boundary treats both as untrusted.

## Enforcement flow

1. Run an LLM as a planner without direct tool credentials.
2. Parse its proposed action into a strict schema.
3. Score untrusted prompts before generation and response/plan drift after
   generation with calibrated detectors.
4. Construct `ActionRequest` using trusted identity and scopes.
5. Call `ActionBoundary.execute()` immediately before the side effect.
6. The registered handler uses narrowly scoped, preferably short-lived
   credentials that were never exposed to the planner.

The boundary denies unregistered tools, unknown arguments, missing scopes,
missing or flagged detector results, policy score vetoes, failed argument
validation, invalid approvals, and audit failure. Write and destructive actions
always require approval.

## Example

```python
from selfguard import (
    ActionBoundary,
    ActionRequest,
    RiskLevel,
    ToolPolicy,
)


def verify_approval(action, token):
    # Verify signature, expiry, principal, action.digest, and one-time use in a
    # trusted approval service. Never accept approval text emitted by the LLM.
    return approval_service.verify(token, expected_digest=action.digest)


boundary = ActionBoundary(
    approval_verifier=verify_approval,
    audit_sink=security_event_sink.emit,
)
boundary.register_tool(
    ToolPolicy(
        tool_name="orders.cancel",
        required_scopes=frozenset({"orders:cancel"}),
        risk_level=RiskLevel.WRITE,
        allowed_argument_names=frozenset({"order_id"}),
        argument_validator=lambda args: (
            isinstance(args["order_id"], str) and args["order_id"].isdigit()
        ),
    ),
    handler=cancel_order_with_scoped_credentials,
)

# proposed_tool and proposed_args came from a schema-validated planner output.
# identity and scopes came from trusted application state.
request = ActionRequest(
    action_id=request_context.action_id,
    principal_id=request_context.user_id,
    tool_name=proposed_tool,
    arguments=proposed_args,
    granted_scopes=request_context.scopes,
    detector_flagged=detection.flagged,
    detector_score=detection.score,
)

# Without a verified token this raises AuthorizationError with
# reason_code="approval_required".
result = boundary.execute(request, approval_token=trusted_approval_token)
```

Approval verifiers receive the exact request and token. Bind authorization to
`request.digest`, principal, expiration, and one-time use so changing arguments
invalidates approval. Audit events contain argument names and a request digest,
not argument values.

### Score prompts before generation

Use `PromptRiskDetector` on the user message and every untrusted retrieved
document before those strings can influence tool selection. If response drift
is also available, combine the evidence conservatively: any flag is a veto and
the boundary receives the maximum score. A low prompt or response score still
does not authorize an action.

```python
prompt_risk = prompt_detector.detect(user_message)
response_risk = response_detector.detect(model_response)

request = ActionRequest(
    action_id=action_id,
    principal_id=principal_id,
    tool_name=proposed_tool,
    arguments=proposed_arguments,
    granted_scopes=trusted_scopes,
    detector_flagged=prompt_risk.flagged or response_risk.flagged,
    detector_score=max(prompt_risk.score, response_risk.score),
)
```

Lexical prompt signals can activate on quoted security discussions and other
hard negatives. Calibrate the learned operating point on representative data;
do not turn individual regex matches into unconditional authorization rules.

## What remains deployment-specific

This primitive does not provide authentication, an approval service, credential
brokering, process/container sandboxing, DLP, network egress control, durable
audit storage, rate limiting, or incident response. Those controls must surround
the executor. Run adversarial tests against the integrated system, not only this
library, before describing the application as a production security boundary.
