"""LangGraph single-main-agent workflow."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from slmagent.contracts.models import Brief
from slmagent.orchestrator.nodes import pipeline as nodes
from slmagent.orchestrator.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("receive_input", nodes.receive_input)
    graph.add_node("plan_creative", nodes.plan_creative)
    graph.add_node("build_storyboard", nodes.build_storyboard)
    graph.add_node("prepare_image_prompt", nodes.prepare_image_prompt)
    graph.add_node("generate_image", nodes.generate_image)
    graph.add_node("check_image", nodes.check_image_node)
    graph.add_node("prepare_video_prompt", nodes.prepare_video_prompt)
    graph.add_node("generate_video", nodes.generate_video)
    graph.add_node("check_video", nodes.check_video_node)
    graph.add_node("postprocess", nodes.postprocess)
    graph.add_node("complete", nodes.complete)

    graph.add_edge(START, "receive_input")
    graph.add_edge("receive_input", "plan_creative")
    graph.add_edge("plan_creative", "build_storyboard")
    graph.add_edge("build_storyboard", "prepare_image_prompt")
    graph.add_edge("prepare_image_prompt", "generate_image")
    graph.add_edge("generate_image", "check_image")
    graph.add_edge("check_image", "prepare_video_prompt")
    graph.add_edge("prepare_video_prompt", "generate_video")
    graph.add_edge("generate_video", "check_video")
    graph.add_edge("check_video", "postprocess")
    graph.add_edge("postprocess", "complete")
    graph.add_edge("complete", END)
    return graph.compile()


def run_pipeline(brief: Brief | dict[str, Any]) -> AgentState:
    if isinstance(brief, dict):
        brief = Brief.model_validate(brief)
    app = build_graph()
    result = app.invoke({"brief": brief})
    return result
