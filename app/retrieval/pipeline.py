from __future__ import annotations

from .hybrid_search import HybridSearcher
from .interfaces import QueryRouter, QueryRewriter, Reranker
from .models import RetrievalResult
from .prompt_assembly import assemble_prompt
from .rerank import NotConfiguredReranker
from .rewrite import PassthroughRewriter
from .router import KeywordScopeRouter


async def retrieve(
    query: str,
    router: QueryRouter | None = None,
    rewriter: QueryRewriter | None = None,
    hybrid_searcher: HybridSearcher | None = None,
    reranker: Reranker | None = None,
    search_top_k: int = 20,
    rerank_top_k: int = 6,
) -> RetrievalResult:
    """Retrieval · online, end to end: Query router -> (stop here if out of scope) ->
    Rewrite query -> Hybrid search -> Rerank -> Prompt assembly."""
    router = router or KeywordScopeRouter()

    decision = await router.route(query)
    if not decision.in_scope:
        # Deliberately don't construct hybrid_searcher/reranker (which stand up a Qdrant
        # client) until scope is confirmed — an out-of-scope query should short-circuit
        # here even if the vector store isn't configured yet, matching the diagram's
        # "no LLM call" refusal path.
        return RetrievalResult(query=query, in_scope=False, router_reason=decision.reason)

    rewriter = rewriter or PassthroughRewriter()
    hybrid_searcher = hybrid_searcher or HybridSearcher()
    reranker = reranker or NotConfiguredReranker()

    rewritten = await rewriter.rewrite(query)
    hits = await hybrid_searcher.search(rewritten.query, top_k=search_top_k)
    reranked = await reranker.rerank(query, hits, top_k=rerank_top_k)
    prompt = assemble_prompt(query, reranked)

    return RetrievalResult(query=query, in_scope=True, router_reason=decision.reason, hits=reranked, prompt=prompt)
