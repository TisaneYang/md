"""Graph construction helpers for the roadside agent workflow."""

from langgraph.graph import END, START, StateGraph

from .state import AgentState


def build_agent_workflow(nodes):
    """Build and compile the LangGraph workflow used by the agent."""
    graph = StateGraph(AgentState)
    graph.add_node("perception", nodes.perception_node)
    graph.add_node("scene_model", nodes.scene_model_node)
    graph.add_node("rule_gate", nodes.rule_gate_node)
    graph.add_node("assessment", nodes.assessment_node)
    graph.add_node("strategy", nodes.strategy_node)
    graph.add_node("task_realization", nodes.task_realization_node)
    graph.add_node("validation", nodes.validation_node)

    graph.add_edge(START, "perception")
    graph.add_edge("perception", "scene_model")
    graph.add_edge("scene_model", "rule_gate")
    graph.add_edge("rule_gate", "assessment")
    graph.add_edge("assessment", "strategy")
    graph.add_edge("strategy", "task_realization")
    graph.add_edge("task_realization", "validation")
    graph.add_edge("validation", END)

    return graph.compile()
