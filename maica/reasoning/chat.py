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

#: How many records get diagnosed to build the chat's evidence bundle. A real
#: account has thousands; diagnosing every one produced a prompt no model could
#: use and a wait no consultant would sit through. The cap is stated in the
#: bundle so the model can say the view is partial rather than imply it is all.
MAX_RECORDS_IN_CHAT_CONTEXT = 40

#: Hard ceiling on the bundle, in characters. Roughly 15k tokens, which leaves
#: room for the system prompt and an answer inside a small local model's
#: context. Without it a 5,000-record account produced a 900,000-character
#: bundle that silently overflowed the window — the model would have answered
#: from whatever fragment survived, with no way to tell.
_MAX_CONTEXT_CHARS = 60_000

#: Only the top-ranked factors per record travel to the model. Lower-ranked
#: ones are, by construction, the ones the ranking already judged weakest.
_MAX_FACTORS_PER_RECORD_IN_CONTEXT = 4

#: A factor can cite dozens of supporting records. The model needs enough to
#: quote and the true total, not the whole list — those arrays were the single
#: largest thing in the bundle.
_MAX_CITED_IDS_IN_CONTEXT = 6

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


def _analysed_record_payload(diagnosis: DiagnosisResult) -> dict:
    return {
        "source_id": diagnosis.target_source_id,
        "ranked_factors": [
            {
                "rank": f.rank,
                "label": f.label.value,
                "summary": f.summary,
                "supporting_source_ids": f.supporting_source_ids[:_MAX_CITED_IDS_IN_CONTEXT],
                "supporting_source_id_count": len(f.supporting_source_ids),
            }
            for f in diagnosis.factors[:_MAX_FACTORS_PER_RECORD_IN_CONTEXT]
        ],
        "gaps": [{"description": g.description, "reason": g.reason} for g in diagnosis.gaps],
    }


def prioritise_source_ids(
    all_source_ids: Sequence[str], focus_source_id: str | None, related_source_ids: Sequence[str]
) -> list[str]:
    """Orders records so the one the consultant is looking at is analysed first,
    then the records it is correlated with, then everything else.

    Without this the bundle is whichever records sort first alphabetically —
    on a 5,000-record account that is 40 arbitrary strangers and never the
    record on screen."""
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in [focus_source_id, *related_source_ids, *all_source_ids]:
        if candidate and candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    known = set(all_source_ids)
    return [source_id for source_id in ordered if source_id in known]


def build_evidence_context(
    records: Sequence[RecordLike],
    diagnoses: Sequence[DiagnosisResult],
    *,
    records_in_analysis: int | None = None,
    focus_source_id: str | None = None,
) -> str:
    """The evidence bundle sent with every question. Deliberately only this
    analysis's own data — llm-rules.md: send only the evidence relevant to the
    question being asked. Takes a list of diagnoses so the same builder serves
    both a single-record chat and a whole-analysis one.

    Trimmed to a fixed character budget, because a real account's evidence is
    far larger than any context window. What was left out is stated in the
    bundle rather than quietly dropped, so the model can say its view is
    partial instead of answering as though it saw everything.
    """
    # Rows for the record in focus (and, next, the ones it is correlated with)
    # go in first, so trimming drops strangers rather than the subject.
    in_bundle = {d.target_source_id for d in diagnoses}
    ordered_records = sorted(
        records,
        key=lambda r: (
            r.source_id != focus_source_id,
            r.source_id not in in_bundle,
        ),
    )
    raw_records = [
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
        for r in ordered_records[:_MAX_RECORDS_IN_CONTEXT]
    ]

    analysed: list[dict] = []
    budget = _MAX_CONTEXT_CHARS - len(json.dumps(raw_records))
    for diagnosis in diagnoses:
        payload = _analysed_record_payload(diagnosis)
        cost = len(json.dumps(payload))
        if analysed and cost > budget:
            break
        analysed.append(payload)
        budget -= cost

    total = records_in_analysis if records_in_analysis is not None else len(diagnoses)
    return json.dumps(
        {
            "coverage": {
                "record_in_focus": focus_source_id,
                "records_analysed_in_this_bundle": len(analysed),
                "records_in_this_analysis": total,
                "is_partial": len(analysed) < total,
                "note": (
                    "This bundle may cover only part of the analysis. If asked about a "
                    "record that is not here, say it is not in this view rather than "
                    "answering from anything else, and say how many records the view "
                    "covers."
                ),
            },
            "records": raw_records,
            "analysed_records": analysed,
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
