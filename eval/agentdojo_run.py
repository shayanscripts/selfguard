"""AgentDojo (v1.2) on the local model: no defence vs SelfGuard v3 action lock.

  python eval/agentdojo_run.py <suite> [n_user_tasks]
Ollama's OpenAI endpoint is used through AgentDojo's LOCAL model (LOCAL_LLM_PORT=11434).
"""
import json
import os
import sys
from collections.abc import Sequence

os.environ.setdefault("LOCAL_LLM_PORT", "11434")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentdojo.agent_pipeline import AgentPipeline, InitQuery, SystemMessage, ToolsExecutionLoop, ToolsExecutor  # noqa: E402
from agentdojo.agent_pipeline.agent_pipeline import get_llm, load_system_message  # noqa: E402
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement  # noqa: E402
from agentdojo.attacks.attack_registry import load_attack  # noqa: E402
from agentdojo.benchmark import benchmark_suite_with_injections, benchmark_suite_without_injections  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402
from agentdojo.logging import OutputLogger  # noqa: E402
from pathlib import Path  # noqa: E402
from selfguard3.actions import ActionLock  # noqa: E402
from selfguard3.values import TrustSet  # noqa: E402

VERSION = "v1.2"


def text_of(msg):
    c = msg.get("content")
    if isinstance(c, list):
        return " ".join(str(p.get("content", p)) if isinstance(p, dict) else str(p) for p in c)
    return c or ""


class ActionLockElement(BasePipelineElement):
    """Drops tool calls whose arguments carry values not found in trusted text
    (system message + user query). No human approver in the benchmark."""
    name = "selfguard3_lock"
    approver = None          # PerimeterApprover or None
    stats = {"tool_calls": 0, "flagged": 0, "approved": 0}

    def query(self, query, runtime, env, messages: Sequence = (), extra_args=None):
        extra_args = extra_args or {}
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1].get("tool_calls"):
            return query, runtime, env, messages, extra_args
        system = " ".join(text_of(m) for m in messages if m["role"] == "system")
        lock = ActionLock(TrustSet(system, query), task=query)
        kept, blocked = [], []
        st = ActionLockElement.stats
        for call in messages[-1]["tool_calls"]:
            st["tool_calls"] += 1
            v = lock.check(call.function, dict(call.args))
            if v.decision != "allow":
                st["flagged"] += 1
                tool_text = " ".join(text_of(m) for m in messages if m["role"] == "tool")
                if self.approver and self.approver(query, call.function, dict(call.args), v, tool_text):
                    st["approved"] += 1
                    v.decision = "allow"
            (kept if v.decision == "allow" else blocked).append(call)
        if blocked:
            extra_args = {**extra_args, "sg3_blocked": extra_args.get("sg3_blocked", 0) + len(blocked)}
            messages = [*messages[:-1], {**messages[-1], "tool_calls": kept or None}]
        return query, runtime, env, messages, extra_args


def pipeline(defended):
    from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
    import openai
    client = openai.OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    llm = OpenAILLM(client, os.environ.get("AD_MODEL", "qwen2.5:7b-instruct"), temperature=0.0)  # native tool calling
    loop = [ToolsExecutor(), llm]
    first = [SystemMessage(load_system_message(None)), InitQuery(), llm]
    if defended:
        el = ActionLockElement()
        if defended == "approver":
            from selfguard3.approver import PerimeterApprover
            el.approver = PerimeterApprover(os.environ.get("AD_APPROVER", "qwen2.5:3b-instruct"))
        first.append(el)
        loop = [ToolsExecutor(), llm, el]
    p = AgentPipeline([*first, ToolsExecutionLoop(loop)])
    p.name = "local"
    return p


def main():
    suite_name = sys.argv[1] if len(sys.argv) > 1 else "banking"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else None
    suite = get_suite(VERSION, suite_name)
    users = list(suite.user_tasks)[:n] if n else None
    out = {}
    conds = os.environ.get("AD_CONDITIONS", "none,sg3").split(",")
    for cond in conds:
        defended = {"none": False, "sg3": True, "approver": "approver"}[cond]
        ActionLockElement.stats = {"tool_calls": 0, "flagged": 0, "approved": 0}
        p = pipeline(defended)
        attack = load_attack("important_instructions", suite, p)
        logdir = Path("runs_agentdojo") / os.environ.get("AD_MODEL", "qwen2.5:7b-instruct").replace(":", "_") / suite_name / cond
        logdir.mkdir(parents=True, exist_ok=True)
        with OutputLogger(str(logdir)):
            clean = benchmark_suite_without_injections(p, suite, logdir=logdir, force_rerun=True, user_tasks=users, benchmark_version=VERSION)
            inj = benchmark_suite_with_injections(p, suite, attack, logdir=logdir, force_rerun=True, user_tasks=users,
                                                  verbose=False, benchmark_version=VERSION)
        key = {"none": "no_defence", "sg3": "selfguard3", "approver": "selfguard3_approver"}[cond]
        u = list(clean["utility_results"].values())
        s = list(inj["security_results"].values())
        ua = list(inj["utility_results"].values())
        out[key] = {"utility_clean": sum(u) / len(u), "attack_success": sum(s) / len(s),
                    "utility_under_attack": sum(ua) / len(ua), "n_clean": len(u), "n_attack": len(s), **ActionLockElement.stats}
        print(key, out[key], flush=True)
    os.makedirs("results", exist_ok=True)
    json.dump(out, open(f"results/agentdojo_{suite_name}_{'_'.join(conds)}_{os.environ.get('AD_MODEL', 'qwen2.5:7b-instruct').replace(':', '_')}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
