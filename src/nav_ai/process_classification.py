"""Evidence-based heuristic domain classification for NAV process candidates.

Labels describe source-code vocabulary, not verified business-process identity.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


_DOMAIN_TERMS = {
    "sales": ("sales", "customer", "ship", "shipment", "sales return", "credit memo"),
    "purchase": ("purchase", "vendor", "receipt", "purchase return"),
    "inventory": ("item journal", "stocktake", "physical inventory", "item ledger", "inventory", "stock"),
    "warehouse": ("warehouse", "bin", "pick", "put-away", "whse"),
    "transfer": ("transfer", "in-transit", "in transit"),
    "finance": ("general journal", "g/l", "ledger", "payment", "bank", "cash", "invoice"),
    "production": ("production", "manufacturing", "routing", "work center", "bom"),
    "service": ("service", "service item", "service order"),
    "job_project": ("job", "project", "resource", "timesheet"),
    "integration": ("xmlport", "edi", "as2", "web service", "integration", "interface", "import", "export"),
    "item_master": ("item", "item category", "brand", "model", "sku"),
    "ownership": ("ownership", "owner", "consignment", "loan", "return loan"),
}


def _contains_term(text: str, term: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    needle = re.sub(r"[^a-z0-9]+", " ", term.casefold()).strip()
    return bool(needle) and f" {needle} " in f" {normalized} "


def classify_process_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return ranked domain hints with explicit lexical evidence and uncertainty."""
    object_text = " ".join(str(candidate.get(key) or "") for key in ("object", "name", "type"))
    procedures = candidate.get("reachable_procedures", [])
    procedure_texts = [str(item.get("node") or "") for item in procedures]
    tables = candidate.get("tables", [])
    table_texts = [
        " ".join((str(item.get("table") or ""), str(item.get("name") or "")))
        for item in tables
    ]
    scores: Counter[str] = Counter()
    evidence: dict[str, list[dict[str, str]]] = {}
    for domain, terms in _DOMAIN_TERMS.items():
        hits: list[dict[str, str]] = []
        for term in terms:
            if _contains_term(object_text, term):
                hits.append({"source": "candidate_object", "term": term})
                scores[domain] += 3
            for text in procedure_texts:
                if _contains_term(text, term):
                    hits.append({"source": "reachable_procedure", "term": term})
                    scores[domain] += 2
            for text in table_texts:
                if _contains_term(text, term):
                    hits.append({"source": "reachable_table", "term": term})
                    scores[domain] += 1
        if hits:
            evidence[domain] = hits

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return {
            "primary_domain": "unclassified",
            "confidence": "insufficient_lexical_evidence",
            "ranked_domains": [],
            "evidence": {},
            "classification_semantics": "heuristic_source_vocabulary_only",
        }
    top_score = ranked[0][1]
    tied = [name for name, score in ranked if score == top_score]
    confidence = "low"
    if len(tied) == 1 and top_score >= 6:
        confidence = "moderate_heuristic"
    elif len(tied) > 1:
        confidence = "ambiguous"
    return {
        "primary_domain": tied[0] if len(tied) == 1 else "ambiguous",
        "confidence": confidence,
        "ranked_domains": [
            {"domain": name, "score": score, "evidence_count": len(evidence[name])}
            for name, score in ranked
        ],
        "evidence": evidence,
        "classification_semantics": "heuristic_source_vocabulary_only",
        "runtime_executed": False,
        "business_process_validated": False,
    }


def classify_process_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a domain hint to each candidate without changing its source evidence."""
    return [
        {**candidate, "domain_classification": classify_process_candidate(candidate)}
        for candidate in candidates
    ]
