"""Optional TypeSafe judgments for decisions that benefit from semantic review."""

from __future__ import annotations

import os
from typing import Any

try:
    from typesafe_sdk import Choice, Noul
except ImportError:
    # Keep the offline dashboard usable before the optional dependency is installed.
    class Choice:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any):
            self.__dict__.update(kwargs)

    class Noul:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any):
            self.__dict__.update(kwargs)


def _evaluate(state: dict[str, Any], questions: dict[str, Any]):
    if not os.environ.get("TYPESAFE_API_KEY"):
        return None
    try:
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        with TypeSafeClient() as client:
            return client.system_one(
                state=state,
                questions=questions,
                timeout=8.0,
                retry=RetryPolicy(max_retries=0),
            )
    except Exception:
        # TypeSafe is an optional decision aid; deterministic application rules
        # remain authoritative when the service or SDK is unavailable.
        return None


def judge_rawmix(
    cement_type: str,
    clinker: dict[str, float],
    diagnostics: list[dict[str, str]],
) -> dict[str, Any]:
    response = _evaluate(
        state={
            "cement_type": cement_type,
            "clinker": clinker,
            "diagnostics": diagnostics,
        },
        questions={
            "recommended_action": Choice(
                instructions="What is the safest next action for this raw-mix result?",
                criteria={
                    "monitor": "The result is acceptable; continue monitoring routine plant data.",
                    "adjust_recipe": "Adjust raw-material proportions or process targets before production.",
                    "stop_and_review": "Do not rely on this result until a qualified engineer reviews the chemistry.",
                },
            ),
            "requires_human_review": Noul(
                instructions="Does this result require qualified human review before production use?",
                criteria={
                    "true": "The chemistry is unsafe, contradictory, physically impossible, or materially uncertain.",
                    "false": "The result is internally consistent and suitable for routine monitoring.",
                },
            ),
        },
    )
    if response is None:
        return {"enabled": False}

    try:
        action = response.choices["recommended_action"]
        review = response.nouls["requires_human_review"]
        review_probability = round(float(review.noul), 3)
        confidence = round(float(action.confidence), 3)
    except (AttributeError, KeyError, TypeError, ValueError):
        return {"enabled": False}

    return {
        "enabled": True,
        "action": action.choice,
        "confidence": confidence,
        "probabilities": action.probabilities,
        "requires_human_review": review_probability >= 0.75,
        "review_probability": review_probability,
    }


def rerank_contexts(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(candidates) < 2:
        return candidates

    response = _evaluate(
        state={
            "query": query,
            "candidates": [
                {"id": i, "text": str(candidate.get("text", ""))[:3000]}
                for i, candidate in enumerate(candidates)
            ],
        },
        questions={
            f"candidate_{i}": Noul(
                instructions=f"Is candidate {i} relevant evidence for answering the query?",
                criteria={
                    "true": "Directly supports an accurate answer to the query.",
                    "false": "Does not materially support an accurate answer to the query.",
                },
            )
            for i in range(len(candidates))
        },
    )
    if response is None:
        return candidates

    try:
        ranked = []
        for i, candidate in enumerate(candidates):
            item = dict(candidate)
            item["typesafe_score"] = round(float(response.nouls[f"candidate_{i}"].noul), 3)
            ranked.append(item)
    except (AttributeError, KeyError, TypeError, ValueError):
        return candidates
    return sorted(ranked, key=lambda item: item["typesafe_score"], reverse=True)


def assess_prediction(
    cement_type: str,
    prediction: float,
    confidence: str,
    r2: float,
    rmse: float,
) -> dict[str, Any]:
    response = _evaluate(
        state={
            "cement_type": cement_type,
            "prediction_mpa": prediction,
            "model_confidence": confidence,
            "validation_r2": r2,
            "validation_rmse_mpa": rmse,
        },
        questions={
            "safe_to_show": Noul(
                instructions="Is this ML strength estimate safe to present as decision-support guidance?",
                criteria={
                    "true": "The estimate has adequate validation evidence and can be shown with its confidence label.",
                    "false": "The estimate is too uncertain or weakly validated and should be reviewed before use.",
                },
            ),
        },
    )
    if response is None:
        return {
            "enabled": False,
            "safe_to_show": None,
            "probability": None,
            "status": "not_reviewed",
        }

    try:
        probability = round(float(response.nouls["safe_to_show"].noul), 3)
    except (AttributeError, KeyError, TypeError, ValueError):
        return {
            "enabled": False,
            "safe_to_show": None,
            "probability": None,
            "status": "not_reviewed",
        }

    is_safe = probability >= 0.75
    return {
        "enabled": True,
        "safe_to_show": is_safe,
        "probability": probability,
        "status": "approved" if is_safe else "rejected",
    }
