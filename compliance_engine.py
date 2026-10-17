"""Compliance engine: flag canonical user queries (user_query_proto.UserQuery) that break a policy.

One rule so far, fair housing: a query must not count, locate, exclude or prefer people by a protected class,
e.g. "Are there too many Asians in our community?". Two stages:
  1. rough filter (regex): does the text mention a protected class at all? Most queries stop here, for free.
  2. final call (a small, cheap LLM; only on stage-1 hits): does it actually target people? Without a classifier,
     or if it fails, the regex rule decides instead: protected term AND a targeting cue (or "without any <group>").
Detection only; acting on a violation is up to the caller.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

from llm_decide import DEFAULT_FALLBACKS, DEFAULT_MODEL, create_with_fallbacks, parse_arguments

from user_query_proto import UserQuery

PROTECTED_CLASSES = {  # US Fair Housing Act classes plus age and sexual orientation (many states and cities)
    "race": r"asians?|(black|white|brown) (people|folks|tenants|residents|families|neighbou?rs)|blacks|whites|"
            r"hispanics?|latin[oax]s?|african americans?|people of colou?r",
    "national_origin": r"immigrants?|foreigners?|people from|mexicans?|chinese|indians?|arabs?|refugees?|"
                       r"undocumented|illegals",
    "religion": r"muslims?|jewish|jews?|christians?|hindus?|sikhs?|buddhists?|catholics?",
    "sex_gender": r"men|women|males?|females?|transgender|trans (people|residents|tenants)",
    "familial_status": r"kids|children|families with|family with|pregnant|babies",
    "disability": r"wheelchairs?|disabled|disabilit(y|ies)|mentally ill|mental illness|blind|deaf|autistic|"
                  r"handicapped",
    "age": r"old people|elderly|seniors|senior citizens|young people",
    "sexual_orientation": r"gay|lesbians?|lgbtq?\+?|queer|bisexual|homosexuals?|same sex",
}
TARGETING_CUES = (  # the question counts, locates or excludes people
    r"too many|how many|which (units?|apartments?|floors?|residents|tenants|neighbou?rs)|who (lives|is living)|"
    r"are there any|avoid|keep .{0,40}\bout\b|stop renting|refuse to rent|(not|n't) rent|only rent|rent only|evict|"
    r"(don't|do not) want|make sure no|get rid of|\bban\b|liv(e|es|ing) (on|in|next)|on my floor|next door|"
    r"next to (me|mine|my)|near me|in (this|our|my|the) (building|community|complex)|new neighbou?rs?")

CLASSIFIER_PROMPT = (
    "You are a fair-housing compliance checker for an apartment resident assistant. Decide whether the resident's "
    "message asks to count, identify, locate, exclude, steer away from, or prefer people because of a protected class "
    f"({', '.join(PROTECTED_CLASSES)}). Requests for accommodations or accessibility, questions about building rules, "
    "and complaints about behavior that merely mention a group are NOT violations. Reply with JSON only: "
    '{"violation": true or false, "category": one of the classes or null, "reason": "<10 words or fewer>"}')
Classify = Callable[[str, list[str]], "dict | None"]  # (text, stage-1 classes) -> verdict, or None if it failed


@dataclass(frozen=True)
class Violation:
    rule: str             # policy broken, e.g. "fair_housing"
    category: str         # e.g. the protected class "race"
    evidence: tuple[str, ...]  # the matched words (and the classifier's reason), for logs and tests
    stage: str = "regex"  # which stage made the call: "regex" or "llm"


def check_query(query: UserQuery, classify: Classify | None = None) -> list[Violation]:
    """Return every policy violation in the query (empty list = compliant). Queries without text are compliant."""
    text = re.sub(r"\s+", " ", (query.text or "").lower().replace("’", "'").replace("-", " "))
    terms = {category: (term.group(0), pattern) for category, pattern in PROTECTED_CLASSES.items()
             if (term := re.search(rf"\b({pattern})\b", text))}
    if not terms:  # stage 1: no protected class mentioned
        return []
    verdict = classify(text, sorted(terms)) if classify else None
    if verdict is not None:  # stage 2: the classifier makes the call
        if verdict.get("violation") is not True:
            return []
        category = verdict.get("category") if verdict.get("category") in PROTECTED_CLASSES else next(iter(terms))
        term = terms.get(category, ("",))[0]
        return [Violation("fair_housing", category, (term, str(verdict.get("reason", ""))), "llm")]
    cue, violations = re.search(TARGETING_CUES, text), []  # no classifier, or it failed: the regex rule decides
    for category, (term, pattern) in terms.items():
        # exclusion right before the group also targets it: "a community without any African Americans"
        excluded = re.search(rf"\b(without|free of|none of the|no more)( any| more| a single)? ({pattern})\b", text)
        if cue or excluded:
            violations.append(Violation("fair_housing", category, (term, (cue or excluded).group(0))))
    return violations


def make_llm_classifier(client=None, model: str | None = None) -> Classify:
    """Stage-2 classifier: one short call to a small model (OPENAI_COMPLIANCE_MODEL, else the agent's OPENAI_MODEL)
    with low reasoning effort. Returns None on any API error or unreadable reply, so the regex rule decides and a
    classifier outage never blocks or crashes a resident's request."""
    models = [model or DEFAULT_MODEL]
    if client is None:
        from openai import OpenAI  # imported lazily so tests run without the package or a key
        from config import get_openai_api_key, load_env_file
        client, env = OpenAI(api_key=get_openai_api_key()), {**load_env_file(), **os.environ}
        models = [model or env.get("OPENAI_COMPLIANCE_MODEL") or env.get("OPENAI_MODEL") or DEFAULT_MODEL] + [
            m.strip() for m in env.get("OPENAI_FALLBACK_MODELS", DEFAULT_FALLBACKS).split(",") if m.strip()]

    def classify(text: str, candidates: list[str]) -> dict | None:
        request = dict(instructions=CLASSIFIER_PROMPT, reasoning={"effort": "low"},
                       input=f"Possible classes: {', '.join(candidates)}\nMessage: {text}")
        try:
            reply = create_with_fallbacks(client, models, request).output_text
        except Exception:
            return None
        verdict, error = parse_arguments(reply)
        return None if error or not isinstance(verdict.get("violation"), bool) else verdict
    return classify
