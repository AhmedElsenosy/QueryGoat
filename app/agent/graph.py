from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    already_published,
    execute_gold,
    fail_run,
    notify_users,
    publish,
    retry,
    rewrite_prompt,
    select_candidate,
    validate_result,
    verify_rewrite,
)
from .state import DailyState


def _after_published(state: DailyState) -> str:
    if state.get("status") == "already_published":
        # Route through notify_users so a skipped/stalled notification is
        # retried; the node is a no-op once notified_at is stamped.
        return "notify_users"
    return "select_candidate"


def _after_select(state: DailyState) -> str:
    if state.get("status") == "failed":
        return "fail_run"
    return "execute_gold"


def _after_validate(state: DailyState) -> str:
    if state.get("status") == "ready_to_publish":
        return "rewrite_prompt"
    return "retry"


def _after_rewrite(state: DailyState) -> str:
    if state.get("status") == "skip_rewrite":
        return "publish"
    return "verify_rewrite"


def _after_verify(state: DailyState) -> str:
    if state.get("status") == "verified":
        return "publish"
    if state.get("status") == "rewrite_retry":
        return "rewrite_prompt"
    return "retry"


def _after_retry(state: DailyState) -> str:
    if state.get("status") == "failed":
        return "fail_run"
    return "select_candidate"


def build_daily_graph():
    graph = StateGraph(DailyState)
    graph.add_node("already_published", already_published)
    graph.add_node("select_candidate", select_candidate)
    graph.add_node("execute_gold", execute_gold)
    graph.add_node("validate_result", validate_result)
    graph.add_node("rewrite_prompt", rewrite_prompt)
    graph.add_node("verify_rewrite", verify_rewrite)
    graph.add_node("retry", retry)
    graph.add_node("publish", publish)
    graph.add_node("notify_users", notify_users)
    graph.add_node("fail_run", fail_run)

    graph.add_edge(START, "already_published")
    graph.add_conditional_edges(
        "already_published",
        _after_published,
        {"end": END, "select_candidate": "select_candidate", "notify_users": "notify_users"},
    )
    graph.add_conditional_edges(
        "select_candidate",
        _after_select,
        {"fail_run": "fail_run", "execute_gold": "execute_gold"},
    )
    graph.add_edge("execute_gold", "validate_result")
    graph.add_conditional_edges(
        "validate_result",
        _after_validate,
        {"rewrite_prompt": "rewrite_prompt", "retry": "retry"},
    )
    graph.add_conditional_edges(
        "rewrite_prompt",
        _after_rewrite,
        {"publish": "publish", "verify_rewrite": "verify_rewrite"},
    )
    graph.add_conditional_edges(
        "verify_rewrite",
        _after_verify,
        {"publish": "publish", "rewrite_prompt": "rewrite_prompt", "retry": "retry"},
    )
    graph.add_conditional_edges(
        "retry",
        _after_retry,
        {"fail_run": "fail_run", "select_candidate": "select_candidate"},
    )
    graph.add_edge("publish", "notify_users")
    graph.add_edge("notify_users", END)
    graph.add_edge("fail_run", END)
    return graph.compile()


daily_graph = build_daily_graph()
