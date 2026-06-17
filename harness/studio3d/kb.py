"""studio3d.kb — a local, dependency-free domain-RAG over DFAM + CSG knowledge.

The report's BlenderRAG finding: retrieval-augmented grounding is most valuable not
as error-prevention but as CAPABILITY-enabling (−26% execution errors AND ~5x more
complex operations). This indexes the bundled knowledge corpus — DFAM numerics, CSG
error→fix pairs, proven recipes, and the registry reference skills — and returns the
most relevant heading-chunks for a query, so the cad-author can author grounded in
documented rules instead of guessing.

No embeddings, no network: a small BM25-style keyword ranker over markdown chunks,
so it runs offline inside the sandboxed/local pipeline.
"""
from __future__ import annotations

import math
import os
import re
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
_KB_DIR = os.path.join(_HERE, "data", "kb")
# registry reference skills (print-readiness, cad-authoring, …) live two levels up
_REGISTRY = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "registry", "skills")

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "for", "on",
         "with", "as", "by", "be", "are", "at", "so", "if", "not", "this", "that"}


def _tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 1]


def _chunk_markdown(text: str, source: str) -> list[dict]:
    """Split markdown into chunks at ## / # headings."""
    chunks = []
    cur_title, cur_lines = source, []
    for line in text.splitlines():
        if re.match(r"^#{1,3}\s", line):
            if cur_lines and any(s.strip() for s in cur_lines):
                chunks.append({"title": cur_title, "source": source,
                               "text": "\n".join(cur_lines).strip()})
            cur_title = re.sub(r"^#+\s*", "", line).strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_lines and any(s.strip() for s in cur_lines):
        chunks.append({"title": cur_title, "source": source, "text": "\n".join(cur_lines).strip()})
    return chunks


@lru_cache(maxsize=1)
def _corpus() -> tuple:
    """Build (chunks, df, n_docs). Cached for the process lifetime."""
    files = []
    for root in (_KB_DIR, _REGISTRY):
        if os.path.isdir(root):
            for dirpath, _dirs, names in os.walk(root):
                for n in names:
                    if n.endswith(".md"):
                        files.append(os.path.join(dirpath, n))
    chunks = []
    for path in sorted(files):
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
        except Exception:
            continue
        src = os.path.relpath(path, os.path.dirname(_HERE))
        for ch in _chunk_markdown(txt, src):
            ch["tokens"] = _tokenize(ch["title"] + " " + ch["text"])
            chunks.append(ch)
    # document frequencies for idf
    df: dict[str, int] = {}
    for ch in chunks:
        for t in set(ch["tokens"]):
            df[t] = df.get(t, 0) + 1
    return chunks, df, max(1, len(chunks))


def search(query: str, k: int = 4) -> list[dict]:
    """Return the top-k knowledge chunks for ``query`` (BM25-ish ranking)."""
    chunks, df, n = _corpus()
    q = _tokenize(query)
    if not q or not chunks:
        return []
    k1, b = 1.5, 0.75
    avg_len = sum(len(c["tokens"]) for c in chunks) / max(1, len(chunks))
    scored = []
    for ch in chunks:
        toks = ch["tokens"]
        if not toks:
            continue
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        dl = len(toks)
        score = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
            denom = tf[t] + k1 * (1 - b + b * dl / avg_len)
            score += idf * (tf[t] * (k1 + 1)) / denom
        # small boost when the query term hits the heading
        title_toks = set(_tokenize(ch["title"]))
        score += 0.5 * sum(1 for t in q if t in title_toks)
        if score > 0:
            scored.append((score, ch))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, ch in scored[:k]:
        out.append({"title": ch["title"], "source": ch["source"],
                    "score": round(s, 3),
                    "text": ch["text"][:1200]})
    return out


def stats() -> dict:
    chunks, df, n = _corpus()
    sources = sorted({c["source"] for c in chunks})
    return {"chunks": len(chunks), "sources": sources, "vocab": len(df)}
