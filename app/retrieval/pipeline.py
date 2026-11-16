from __future__ import annotations

from functools import lru_cache

from .hybrid_search import HybridSearcher
from .interfaces import QueryRouter, QueryRewriter, Reranker
from .models import ChatTurn, RetrievalResult
from .prompt_assembly import assemble_user_message
from .rerank import CrossEncoderReranker
from .rewrite import LLMQueryRewriter
from .router import LLMScopeRouter


# Process-wide defaults. The embedder and the reranker hold large ONNX models that load
# lazily on first use and are then kept on the instance, so the instances themselves must
# outlive the request: building a new one per /query reloaded both models every time
# (~20s + ~35s on a 4-CPU container) before the generation LLM was even called.
@lru_cache(maxsize=1)
def _default_hybrid_searcher() -> HybridSearcher:
    return HybridSearcher()


@lru_cache(maxsize=1)
def _default_reranker() -> Reranker:
    return CrossEncoderReranker()


async def retrieve(
    query: str,
    history: list[ChatTurn] | None = None,
    history_summary: str | None = None,
    router: QueryRouter | None = None,
    rewriter: QueryRewriter | None = None,
    hybrid_searcher: HybridSearcher | None = None,
    reranker: Reranker | None = None,
    search_top_k: int = 20,
    rerank_top_k: int = 6,
) -> RetrievalResult:
    """Retrieval · online, end to end: Query router -> (stop here if out of scope) ->
    Rewrite query -> Hybrid search -> Rerank -> Prompt assembly. `history` should already
    be capped (see generation/memory.py's fold_history) — it's used here for pronoun
    resolution and is otherwise just carried through on RetrievalResult for
    generation/pipeline.py to build the final multi-turn message list from.

    The default router (LLMScopeRouter) spends one cheap/local LLM call per message to
    decide scope and, in the same call, write either the rewritten search query (in
    scope) or the reply to show the user (small talk / out of scope); general finance
    questions are flagged and rewritten into a self-contained question, which
    generation/pipeline.py answers without retrieval. The separate
    rewriter only runs when the router didn't supply a rewritten query; see
    retrieval/router.py."""
    router = router or LLMScopeRouter()
    history = history or []

    decision = await router.route(query, history)
    if not decision.in_scope:
        # Deliberately don't construct hybrid_searcher/reranker (which stand up a Qdrant
        # client) until scope is confirmed — an out-of-scope query should short-circuit
        # here even if the vector store isn't configured yet.
        return RetrievalResult(
            query=query,
            in_scope=False,
            router_reason=decision.reason,
            courtesy=decision.courtesy,
            general_finance=decision.general_finance,
            reply=decision.reply,
            rewritten_query=decision.rewritten_query if decision.general_finance else None,
            history=history,
            history_summary=history_summary,
        )

    hybrid_searcher = hybrid_searcher or _default_hybrid_searcher()
    reranker = reranker or _default_reranker()

    rewritten_query = decision.rewritten_query
    if not rewritten_query:
        rewritten_query = (await (rewriter or LLMQueryRewriter()).rewrite(query, history)).query
    hits = await hybrid_searcher.search(rewritten_query, top_k=search_top_k)
    reranked = await reranker.rerank(query, hits, top_k=rerank_top_k)
    prompt = assemble_user_message(query, reranked)

    return RetrievalResult(
        query=query,
        in_scope=True,
        router_reason=decision.reason,
        rewritten_query=rewritten_query,
        hits=reranked,
        prompt=prompt,
        history=history,
        history_summary=history_summary,
    )
