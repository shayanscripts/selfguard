import unittest

from selfguard import (
    ActionBoundary,
    ActionRequest,
    AuthorizationError,
    Decision,
    RiskLevel,
    ToolPolicy,
)


def request(**overrides):
    values = {
        "action_id": "action-1",
        "principal_id": "user-1",
        "tool_name": "orders.read",
        "arguments": {"order_id": "123"},
        "granted_scopes": frozenset({"orders:read"}),
        "detector_flagged": False,
        "detector_score": 0.1,
    }
    values.update(overrides)
    return ActionRequest(**values)


class ActionBoundaryTests(unittest.TestCase):
    def test_tool_arguments_are_deep_copied_and_immutable(self):
        original = {"filters": [{"status": "open"}]}
        action = request(arguments=original)
        digest = action.digest
        original["filters"][0]["status"] = "closed"
        self.assertEqual(action.arguments_copy()["filters"][0]["status"], "open")
        self.assertEqual(action.digest, digest)
        with self.assertRaises(TypeError):
            action.arguments["new"] = True

    def test_argument_acceptance_requires_a_validator(self):
        with self.assertRaisesRegex(ValueError, "argument_validator"):
            ToolPolicy(
                "orders.read",
                allowed_argument_names=frozenset({"order_id"}),
            )

    def test_unknown_tools_are_denied(self):
        decision = ActionBoundary().authorize(request())
        self.assertEqual(decision.decision, Decision.DENY)
        self.assertEqual(decision.reason_code, "tool_not_registered")

    def test_low_detector_score_does_not_override_missing_scope(self):
        boundary = ActionBoundary()
        boundary.register_tool(
            ToolPolicy(
                "orders.read",
                required_scopes=frozenset({"orders:read"}),
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: isinstance(args["order_id"], str),
            ),
            lambda order_id: order_id,
        )
        decision = boundary.authorize(request(granted_scopes=frozenset()))
        self.assertEqual(decision.reason_code, "missing_scope")
        self.assertEqual(decision.missing_scopes, frozenset({"orders:read"}))

    def test_detector_result_is_required_and_flag_is_a_veto(self):
        boundary = ActionBoundary()
        boundary.register_tool(
            ToolPolicy(
                "orders.read",
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: isinstance(args["order_id"], str),
            ),
            lambda order_id: order_id,
        )
        missing = boundary.authorize(
            request(detector_flagged=None, detector_score=None, granted_scopes=frozenset())
        )
        flagged = boundary.authorize(
            request(detector_flagged=True, detector_score=0.9, granted_scopes=frozenset())
        )
        self.assertEqual(missing.reason_code, "detector_result_missing")
        self.assertEqual(flagged.reason_code, "detector_flagged")

    def test_read_only_action_executes_after_all_policy_checks(self):
        boundary = ActionBoundary()
        boundary.register_tool(
            ToolPolicy(
                "orders.read",
                required_scopes=frozenset({"orders:read"}),
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: args["order_id"].isdigit(),
            ),
            lambda order_id: {"order_id": order_id},
        )
        self.assertEqual(boundary.execute(request()), {"order_id": "123"})

    def test_unexpected_argument_is_denied(self):
        boundary = ActionBoundary()
        boundary.register_tool(
            ToolPolicy(
                "orders.read",
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: isinstance(args["order_id"], str),
            ),
            lambda order_id: order_id,
        )
        decision = boundary.authorize(
            request(arguments={"order_id": "123", "admin": True})
        )
        self.assertEqual(decision.reason_code, "argument_not_allowed")

    def test_write_actions_require_verified_approval(self):
        def verify(action, token):
            return token == f"approved:{action.digest}"

        boundary = ActionBoundary(approval_verifier=verify)
        boundary.register_tool(
            ToolPolicy(
                "orders.cancel",
                required_scopes=frozenset({"orders:cancel"}),
                risk_level=RiskLevel.WRITE,
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: isinstance(args["order_id"], str),
            ),
            lambda order_id: f"cancelled:{order_id}",
        )
        action = request(
            tool_name="orders.cancel",
            granted_scopes=frozenset({"orders:cancel"}),
        )
        pending = boundary.authorize(action)
        self.assertEqual(pending.decision, Decision.REQUIRE_APPROVAL)
        self.assertEqual(
            boundary.execute(action, approval_token=f"approved:{action.digest}"),
            "cancelled:123",
        )

    def test_approval_is_bound_to_exact_arguments(self):
        approved_digest = request(
            tool_name="orders.cancel",
            granted_scopes=frozenset({"orders:cancel"}),
        ).digest
        boundary = ActionBoundary(
            approval_verifier=lambda action, token: token == f"approved:{action.digest}"
        )
        boundary.register_tool(
            ToolPolicy(
                "orders.cancel",
                required_scopes=frozenset({"orders:cancel"}),
                risk_level=RiskLevel.WRITE,
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: isinstance(args["order_id"], str),
            ),
            lambda order_id: order_id,
        )
        tampered = request(
            tool_name="orders.cancel",
            arguments={"order_id": "999"},
            granted_scopes=frozenset({"orders:cancel"}),
        )
        decision = boundary.authorize(
            tampered, approval_token=f"approved:{approved_digest}"
        )
        self.assertEqual(decision.reason_code, "approval_invalid")

    def test_audit_records_metadata_without_argument_values(self):
        events = []
        boundary = ActionBoundary(audit_sink=events.append)
        boundary.register_tool(
            ToolPolicy(
                "orders.read",
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: isinstance(args["order_id"], str),
            ),
            lambda order_id: order_id,
        )
        boundary.authorize(request(granted_scopes=frozenset()))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].argument_names, ("order_id",))
        self.assertNotIn("123", repr(events[0]))

    def test_audit_failure_is_fail_closed_by_default(self):
        def broken_audit(_event):
            raise RuntimeError("offline")

        boundary = ActionBoundary(audit_sink=broken_audit)
        boundary.register_tool(
            ToolPolicy(
                "orders.read",
                allowed_argument_names=frozenset({"order_id"}),
                argument_validator=lambda args: isinstance(args["order_id"], str),
            ),
            lambda order_id: order_id,
        )
        decision = boundary.authorize(request(granted_scopes=frozenset()))
        self.assertEqual(decision.reason_code, "audit_unavailable")
        with self.assertRaises(AuthorizationError):
            boundary.execute(request(granted_scopes=frozenset()))


if __name__ == "__main__":
    unittest.main()
