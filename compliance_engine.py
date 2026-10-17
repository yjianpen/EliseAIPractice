"""Compliance engine: flag canonical user queries (user_query_proto.UserQuery) that break a policy.

v1 covers one rule, fair housing: a query is flagged when its text mentions a protected class AND targets people
with it (counting, locating or excluding residents), e.g. "Are there too many Asians in our community?". Requiring
both keeps ordinary requests unflagged: "Is the elevator wheelchair accessible?", "black mold in my bathroom".
Detection only (deterministic keyword rules, no LLM call); acting on a violation is up to the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Violation:
    rule: str             # policy broken, e.g. "fair_housing"
    category: str         # e.g. the protected class "race"
    evidence: tuple[str, ...]  # the matched words, for logs and tests


def check_query(query: UserQuery) -> list[Violation]:
    """Return every policy violation in the query (empty list = compliant). Queries without text are compliant."""
    text = re.sub(r"\s+", " ", (query.text or "").lower().replace("’", "'").replace("-", " "))
    cue = re.search(TARGETING_CUES, text)
    if not cue:
        return []
    return [Violation("fair_housing", category, (term.group(0), cue.group(0)))
            for category, pattern in PROTECTED_CLASSES.items() if (term := re.search(rf"\b({pattern})\b", text))]
