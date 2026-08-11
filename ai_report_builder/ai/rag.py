"""RAG for documentation — answer "how do I..." questions (Beyond-MVP #6).

Chunks are stored as AI Knowledge Chunk records with an optional embedding
(Ollama `nomic-embed-text`). Retrieval uses cosine similarity when embeddings
are available and falls back to keyword overlap, so it works even without the
embedding model. The answer is grounded strictly in retrieved context.
"""

import json
import math
import re

import frappe

from ai_report_builder.ai.prompts import DOC_ANSWER_PROMPT

EMBED_URL = "http://localhost:11434/v1"  # local Ollama, independent of chat provider
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 600
TOP_K = 4


def _embed(texts):
    """Embed a list of texts via Ollama. Returns list of vectors or None."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key="ollama", base_url=EMBED_URL)
        resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [d.embedding for d in resp.data]
    except Exception:
        return None


def _chunk(content):
    """Pack paragraphs into ~CHUNK_SIZE-char chunks."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 1 > CHUNK_SIZE:
            chunks.append(cur.strip())
            cur = ""
        cur += (" " if cur else "") + p
    if cur.strip():
        chunks.append(cur.strip())
    return chunks or [content.strip()]


def ingest(title, content, source=None):
    """Chunk + embed + store an article. Returns number of chunks stored."""
    chunks = _chunk(content)
    embs = _embed(chunks) or [None] * len(chunks)
    for ch, emb in zip(chunks, embs):
        frappe.get_doc(
            {
                "doctype": "AI Knowledge Chunk",
                "title": title,
                "source": source or title,
                "content": ch,
                "embedding": json.dumps(emb) if emb else None,
            }
        ).insert(ignore_permissions=True)
    frappe.db.commit()
    return len(chunks)


def _clean_markdown(text):
    """Strip markdown noise so chunks are clean prose for embedding/retrieval."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)  # html comments
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links -> text
    text = re.sub(r"^\s*>.*$", "", text, flags=re.MULTILINE)  # breadcrumb quotes
    text = re.sub(r"[#*`]", "", text)  # md symbols
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title_from_md(text, fallback):
    m = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else fallback


def ingest_markdown_dir(path, source="ERPNext manual", exclude=None, progress_every=50):
    """Walk a directory of .md files and ingest each as an article.
    Returns (files_ingested, chunks_stored)."""
    import os

    exclude = exclude or {"index.md", "contents.md", "translations.md"}
    files = chunks = skipped = 0
    for root, _dirs, names in os.walk(path):
        for fn in names:
            if not fn.endswith(".md") or fn in exclude:
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    raw = fh.read()
                clean = _clean_markdown(raw)
                if len(clean) < 40:
                    continue
                title = _title_from_md(
                    raw, fn[:-3].replace("-", " ").replace("_", " ").title()
                )
                chunks += ingest(title, clean, source=source)
                files += 1
                if files % progress_every == 0:
                    print(f"  ingested {files} files, {chunks} chunks...")
            except Exception as e:
                skipped += 1
                frappe.logger("ai_report_builder").warning(f"skip {fn}: {e}")
    print(f"  skipped {skipped} files")
    return files, chunks


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keyword_score(query, text):
    q = set(re.findall(r"\w+", query.lower()))
    words = re.findall(r"\w+", text.lower())
    if not q or not words:
        return 0.0
    return sum(1 for w in words if w in q) / math.sqrt(len(words))


def retrieve(query, k=TOP_K):
    """Return the top-k most relevant chunks (cosine if embedded, else keyword)."""
    chunks = frappe.get_all(
        "AI Knowledge Chunk", fields=["name", "title", "source", "content", "embedding"]
    )
    if not chunks:
        return []

    qemb = _embed([query])
    qvec = qemb[0] if qemb else None

    scored = []
    for c in chunks:
        score = None
        if qvec and c.embedding:
            try:
                score = _cosine(qvec, json.loads(c.embedding))
            except Exception:
                score = None
        if score is None:
            score = _keyword_score(query, c.content)
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored[:k] if s > 0]


def answer_doc_question(question, provider=None):
    """Retrieve context and answer grounded strictly in it."""
    from ai_report_builder.ai.provider import get_provider_chain
    from ai_report_builder.ai.query import _complete

    hits = retrieve(question)
    if not hits:
        return {
            "answer": "I don't have documentation on that yet.",
            "sources": [],
            "error": None,
        }

    context = "\n\n".join(f"[{h.title}] {h.content}" for h in hits)
    sources = list(dict.fromkeys(h.title for h in hits))
    prompt = DOC_ANSWER_PROMPT.format(context=context, question=question)
    try:
        chain = get_provider_chain(provider)
        msg = _complete(chain, [{"role": "user", "content": prompt}])
        return {"answer": (msg.content or "").strip(), "sources": sources, "error": None}
    except Exception:
        return {"answer": None, "sources": sources, "error": "provider_unavailable"}
