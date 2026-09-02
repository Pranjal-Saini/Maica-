"""Grounded Q&A over one analysis's evidence.

Same principle as the narrator in llm.py: the model discusses evidence, it is
not the source of truth (reasoning-rules.md). It is given only this analysis's
records, ranked factors and gaps, and is told to say so plainly when the
evidence does not answer a question — rather than reaching for general
NetSuite knowledge it does not reliably have (hard-rules.md forbids inventing
NetSuite behaviour).
"""

import json
from collections.abc import Sequence

from pydantic import BaseModel

from maica.graph.builder import RecordLike
from maica.reasoning.llm import LLMClient, LLMRequestError, LLMTimeoutError
from maica.reasoning.models import DiagnosisResult

CHAT_PROMPT_VERSION = "v1"

_MAX_RECORDS_IN_CONTEXT = 200
_MAX_HISTORY_TURNS = 6

_SYSTEM_PROMPT = f"""You are helping a NetSuite consultant interpret evidence \
that has already been collected and analysed for one transaction. You are given \
that evidence below as JSON: the normalized records, the ranked contributing \
factors, and the gaps (things the evidence cannot answer).

Rules you must follow exactly:
- Answer ONLY from the evidence given to you. Never use general knowledge about \
how NetSuite works to fill a gap — if the evidence does not answer the question, \
say plainly that this evidence does not show it, and point at the relevant gap.
- Never invent record IDs, field names, values, scripts, workflows or users. Only \
refer to what appears in the evidence.
- Never claim something caused the outcome. The factors are ranked by support, \
not proven as causes; a change or a shared value is not proof of causation.
- Do not re-rank or contradict the factor labels you were given.
- Cite the record IDs or field names you are drawing on, so the consultant can \
check you.
- Be brief and plain. Two or three sentences is usually enough.

Prompt version: {CHAT_PROMPT_VERSION}"""


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatAnswer(BaseModel):
    answer: str
    grounded: bool  # False when the model was unavailable and this is a canned reply


def build_evidence_context(
    records: Sequence[RecordLike], diagnoses: Sequence[DiagnosisResult]
) -> str:
    """The evidence bundle sent with every question. Deliberately only this
    analysis's own data — llm-rules.md: send only the evidence relevant to the
    question being asked. Takes a list of diagnoses so the same builder serves
    both a single-record chat and a whole-analysis one."""
    return json.dumps(
        {
            "records": [
                {
                    "source_id": r.source_id,
                    "record_type": r.record_type,
                    "field_name": r.field_name,
                    "old_value": r.old_value,
                    "new_value": r.new_value,
                    "actor": r.actor,
                    "context": r.context,
                    "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                }
                for r in records[:_MAX_RECORDS_IN_CONTEXT]
            ],
            "analysed_records": [
                {
                    "source_id": d.target_source_id,
                    "ranked_factors": [
                        {
                            "rank": f.rank,
                            "label": f.label.value,
                            "summary": f.summary,
                            "supporting_source_ids": f.supporting_source_ids,
                        }
                        for f in d.factors
                    ],
                    "gaps": [{"description": g.description, "reason": g.reason} for g in d.gaps],
                }
                for d in diagnoses
            ],
        }
    )


def _build_user_content(
    evidence_context: str, history: Sequence[ChatMessage], question: str
) -> str:
    recent = list(history)[-_MAX_HISTORY_TURNS:]
    transcript = "\n".join(f"{m.role}: {m.content}" for m in recent)
    parts = [f"EVIDENCE:\n{evidence_context}"]
    if transcript:
        parts.append(f"EARLIER IN THIS CONVERSATION:\n{transcript}")
    parts.append(f"QUESTION:\n{question}")
    return "\n\n".join(parts)


async def answer_question(
    question: str,
    *,
    evidence_context: str,
    history: Sequence[ChatMessage],
    client: LLMClient | None,
    model: str,
) -> ChatAnswer:
    """Answers one question about one analysis's evidence. A missing client or
    a failed call returns a plain, honest message rather than raising — the
    rest of the report stays usable either way."""
    if client is None:
        return ChatAnswer(
            answer=(
                "The assistant is not available right now (no language model is "
                "configured on this server). The ranked factors and gaps on this "
                "analysis are unaffected."
            ),
            grounded=False,
        )

    try:
        raw = await client.complete(
            model=model,
            system=_SYSTEM_PROMPT,
            user=_build_user_content(evidence_context, history, question),
            json_mode=False,  # this answer is prose for a human, not a parsed schema
        )
    except LLMTimeoutError:
        return ChatAnswer(
            answer=(
                "The assistant took too long to answer. It is probably still working "
                "through this page's factors — wait a few seconds and ask again. The "
                "ranked factors and gaps on this analysis are unaffected."
            ),
            grounded=False,
        )
    except LLMRequestError:
        return ChatAnswer(
            answer=(
                "The assistant could not be reached just now — check the language "
                "model server is running. The ranked factors and gaps on this "
                "analysis are unaffected."
            ),
            grounded=False,
        )

    return ChatAnswer(answer=raw.strip(), grounded=True)
