from __future__ import annotations

import re
import unicodedata
from html import escape

from markdown_it import MarkdownIt

from kfabric.infra.models import Corpus


MARKDOWN_RENDERER = MarkdownIt("commonmark", {"html": False, "linkify": True, "breaks": True})


def render_corpus_html(corpus: Corpus) -> str:
    rendered_markdown = MARKDOWN_RENDERER.render(corpus.corpus_markdown)
    safe_title = escape(corpus.title)
    status = escape(corpus.status)
    export_name = escape(export_filename(corpus, "html"))
    return f"""<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <meta name="generator" content="KFabric">
    <meta name="export-name" content="{export_name}">
    <style>
      :root {{
        color-scheme: light;
        --bg: #eef3fb;
        --panel: #ffffff;
        --line: #d7e0ef;
        --ink: #11203b;
        --muted: #5d6c89;
        --accent: #1b6fe5;
        --accent-soft: #e9f2ff;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top, rgba(27,111,229,0.12), transparent 35%),
          linear-gradient(180deg, #f6f9ff 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      .page {{
        max-width: 960px;
        margin: 0 auto;
        padding: 40px 24px 80px;
      }}
      .hero {{
        background: linear-gradient(135deg, #10203d 0%, #17386d 100%);
        color: white;
        border-radius: 24px;
        padding: 28px 30px;
        box-shadow: 0 22px 60px rgba(16, 32, 61, 0.18);
      }}
      .hero small {{
        display: inline-block;
        margin-top: 10px;
        color: rgba(255,255,255,0.78);
      }}
      .hero p {{
        margin: 10px 0 0;
        color: rgba(255,255,255,0.88);
      }}
      .content {{
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        margin-top: 20px;
        padding: 32px;
        box-shadow: 0 16px 40px rgba(21, 44, 84, 0.08);
      }}
      h1, h2, h3 {{ color: var(--ink); }}
      h1 {{ margin: 0; font-size: 2.1rem; }}
      h2 {{
        margin-top: 2.2rem;
        padding-top: 0.6rem;
        border-top: 1px solid var(--line);
      }}
      h3 {{
        margin-top: 1.6rem;
        background: var(--accent-soft);
        padding: 0.7rem 0.9rem;
        border-radius: 14px;
      }}
      p, li {{
        line-height: 1.68;
        color: var(--ink);
      }}
      ul {{
        padding-left: 1.2rem;
      }}
      blockquote {{
        margin: 1rem 0;
        padding: 0.9rem 1rem;
        border-left: 4px solid var(--accent);
        background: #f7fbff;
        color: var(--muted);
        border-radius: 0 14px 14px 0;
      }}
      code {{
        background: #edf3ff;
        border-radius: 6px;
        padding: 0.1rem 0.35rem;
      }}
      a {{
        color: var(--accent);
      }}
    </style>
  </head>
  <body>
    <main class="page">
      <section class="hero">
        <h1>{safe_title}</h1>
        <p>Export corpus KFabric, format demonstration lisible pour revue humaine.</p>
        <small>Statut : {status}</small>
      </section>
      <article class="content">
        {rendered_markdown}
      </article>
    </main>
  </body>
</html>
"""


def export_filename(corpus: Corpus, extension: str) -> str:
    slug = _slugify(corpus.title or corpus.id)
    return f"{slug or corpus.id}.{extension}"


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return normalized[:80]
