from fastmcp import FastMCP
from schema import InsightRecommendation
from retreival import pipeline
from synthesis import synthesize_insight

mcp = FastMCP("coursera-insight-pipeline")


@mcp.tool()
# Exposes the retrieve+synthesize pipeline as one MCP tool so an agent can request insights over the protocol.
def generate_insight(query: str, top_k: int = 4) -> InsightRecommendation:
    """
    Given a learner-friction question, retrieves cross-modal evidence using
    Qdrant dense vector search followed by Cohere reranking, then synthesizes
    a structured, cited InsightRecommendation for review.
    """
    reranked_chunks = pipeline.retrieve_and_rerank(query=query, top_k=top_k)
    return synthesize_insight(query, reranked_chunks)


if __name__ == "__main__":
    # Pre-initialize retrieval indices on server startup
    pipeline.initialize()
    mcp.run()