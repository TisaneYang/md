"""Graph construction helpers for Agent2 workflow."""

from langgraph.graph import END, START, StateGraph

from .state import Agent2State


def build_agent2_workflow(nodes):
    """Build and compile Agent2 workflow from the design sketch."""
    graph = StateGraph(Agent2State)
    graph.add_node("perception_normalize", nodes.perception_normalize_node)
    graph.add_node("scene_model_extract", nodes.scene_model_extract_node)               # llm 带图
    graph.add_node("destination_navigate", nodes.destination_navigate)
    graph.add_node("maneuver_sequence_planning", nodes.maneuver_sequence_planning_node) 
    graph.add_node("output_validation", nodes.output_validation_node)

    graph.add_edge(START, "perception_normalize")
    graph.add_edge("perception_normalize", "scene_model_extract")
    graph.add_edge("scene_model_extract", "destination_navigate")
    graph.add_edge("destination_navigate", "maneuver_sequence_planning")
    graph.add_edge("maneuver_sequence_planning", "output_validation")
    graph.add_edge("output_validation", END)

    return graph.compile()
