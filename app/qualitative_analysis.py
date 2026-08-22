from __future__ import annotations

import re
from typing import Any


def parse_codebook(raw: str) -> list[dict[str, Any]]:
    codes=[]
    for line in str(raw or "").splitlines():
        text=line.strip()
        if not text: continue
        if ":" in text:
            code,keywords=text.split(":",1)
        else:
            code,keywords=text,text
        kws=[k.strip().lower() for k in re.split(r"[,;|]",keywords) if k.strip()]
        codes.append({"code":code.strip()[:120],"keywords":kws[:30]})
    return codes[:100]


def code_transcript(text: str, codebook: list[dict[str, Any]]) -> dict[str, Any]:
    sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+",str(text or "")) if len(s.strip())>=15]
    matches=[]
    for idx,sentence in enumerate(sentences,1):
        low=sentence.lower()
        for code in codebook:
            kws=code.get("keywords") or []
            hit=[k for k in kws if k and k in low]
            if hit:
                matches.append({"segment_id":idx,"code":code.get("code"),"matched_keywords":hit,"excerpt":sentence[:1800]})
    counts={}
    for m in matches: counts[m["code"]]=counts.get(m["code"],0)+1
    return {"segments":len(sentences),"coded_segments":len({m['segment_id'] for m in matches}),"matches":matches[:3000],"code_counts":[{"code":k,"count":v} for k,v in sorted(counts.items(),key=lambda x:(-x[1],x[0]))]}


def integration_matrix(quantitative_findings: list[dict[str, Any]], qualitative_themes: list[dict[str, Any]]) -> dict[str, Any]:
    rows=[]
    maxlen=max(len(quantitative_findings),len(qualitative_themes),1)
    for i in range(maxlen):
        q=quantitative_findings[i] if i<len(quantitative_findings) else {}
        t=qualitative_themes[i] if i<len(qualitative_themes) else {}
        rows.append({"objective":q.get("objective") or t.get("objective") or f"Objective {i+1}","quantitative_finding":q.get("finding") or "","qualitative_theme":t.get("theme") or "","integration_note":t.get("integration_note") or q.get("integration_note") or "Researcher to classify as convergence, complementarity, divergence or expansion."})
    return {"rows":rows,"rule":"ProjectReady organises the integration matrix but does not invent qualitative themes, quotations or quantitative findings."}
