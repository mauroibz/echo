"""Summary templates: what sections a kind of meeting wants (stdlib only).

A template replaces the summary prompt's guidance on sections; every other rule (bullets, names,
length, next steps, language) stays. A recording takes the template named by its tag in the
category `template` (`template:entrevista`), else the general one. Echo ships a few in Spanish;
the user's own are Markdown files in `<config>/studio/templates/<name>.md` and win over a
built-in with the same name.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from echo_app import paths
from echo_app.library import Recording, fold_tag, tag_category

CATEGORY = "template"

GENERAL = """- Group the content by topic, not in the order it was said, in 4 to 7 sections, each with a
  single # heading. Use no ## or ### headings."""

BUILT_IN = {
    "uno-a-uno": """- Es una reunión uno a uno. Usá estas secciones, cada una con un único encabezado #, y omití
  las que no tengan contenido: "Cómo está", "Avances", "Bloqueos", "Feedback" (en ambos
  sentidos) y "Acuerdos". No uses encabezados ## ni ###.""",
    "entrevista": """- Es una entrevista. Una sección con encabezado # por pregunta importante, en el orden en
  que se hicieron, con la respuesta resumida debajo; al final, una sección "Impresiones" con lo
  que la respuesta dejó ver (fortalezas, dudas, señales). No uses encabezados ## ni ###.""",
    "clase": """- Es una clase o charla. Secciones con encabezado # por concepto enseñado, en el orden en que
  se dieron, con definiciones y ejemplos debajo; al final, "Para hacer" con tareas, lecturas y
  fechas que se dieron. No uses encabezados ## ni ###.""",
    "cliente": """- Es una reunión con un cliente. Usá estas secciones, cada una con un único encabezado #, y
  omití las que no tengan contenido: "Contexto del cliente", "Necesidades y problemas",
  "Lo que ofrecimos", "Objeciones y dudas", "Precios y condiciones" y "Acuerdos". No uses
  encabezados ## ni ###.""",
}


def user_dir() -> Path:
    return paths.config_dir() / "studio" / "templates"


def names() -> list[str]:
    """Every template's name, built-in and the user's, sorted."""
    own = {p.stem for p in user_dir().glob("*.md")} if user_dir().is_dir() else set()
    return sorted(set(BUILT_IN) | own, key=fold_tag)


def text(name: str) -> str | None:
    """The template's guidance, the user's file first; None if there is no such template. Names
    match as tags do (`template:Entrevista` is `entrevista`)."""
    want = fold_tag(name)
    if user_dir().is_dir():
        for p in user_dir().glob("*.md"):
            if fold_tag(p.stem) == want:
                try:
                    t = p.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if t:
                    return t
    return next((t for n, t in BUILT_IN.items() if fold_tag(n) == want), None)


def of(rec: Recording) -> str | None:
    """The template the recording's tags name (the first `template:` tag), or None."""
    for tag in rec.meta.tags:
        cat = tag_category(tag)
        if cat and fold_tag(cat[0]) == CATEGORY:
            return cat[1]
    return None


def resolve(rec: Recording, name: str | None = None) -> tuple[str | None, str]:
    """(template name or None for the general one, its guidance). An unknown name is general."""
    name = name if name is not None else of(rec)
    t = text(name) if name else None
    return (name, t) if t else (None, GENERAL)


def sha(guidance: str) -> str:
    return hashlib.sha256(guidance.encode("utf-8")).hexdigest()


def set_for(rec: Recording, name: str | None) -> None:
    """Make `name` the recording's template (None: the general one), as its `template:` tag."""
    tags = [t for t in rec.meta.tags if not ((c := tag_category(t)) and fold_tag(c[0]) == CATEGORY)]
    if name:
        tags.append(f"{CATEGORY}:{name}")
    rec.set_tags(tags)
