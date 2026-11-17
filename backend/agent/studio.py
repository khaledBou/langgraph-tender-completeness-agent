"""Entry point for LangGraph Studio and the LangGraph Agent Server.

`langgraph dev` reads langgraph.json, imports this module and serves the graph.
The server supplies its own checkpointer, so none is attached here.
"""

from agent.graph import build_graph

graph = build_graph()
