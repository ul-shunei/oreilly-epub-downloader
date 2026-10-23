"""HTML folder generation from O'Reilly book content."""

from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from rich.console import Console

from .epub import (
    _chapter_basename,
    _escape_html,
    _extract_body_content,
    _get_default_css,
    _guess_image_extension,
)
from .models import Book, Chapter

console = Console()

NAV_CSS = """
/* Chapter navigation */
nav.chapter-nav {
    display: flex;
    justify-content: space-between;
    gap: 1em;
    margin: 1em 0;
    padding: 0.5em 0;
    border-top: 1px solid #ddd;
    border-bottom: 1px solid #ddd;
    font-family: Helvetica, Arial, sans-serif;
    font-size: 0.9em;
}

.cover {
    max-width: 300px;
}
"""


def create_html(book: Book, output_dir: Path) -> Path:
    """Create a folder of HTML pages from book content.

    Writes one HTML file per chapter, an index.html table of contents,
    the stylesheet, cover and images.

    Args:
        book: Complete book with metadata and chapters
        output_dir: Directory to write the HTML files into

    Returns:
        Path to the generated index.html
    """
    console.print(f"[bold]Creating HTML: {book.metadata.title}[/]")

    chapters = [c for c in book.chapters if len(c.html_content.strip()) >= 50]
    skipped = len(book.chapters) - len(chapters)
    if skipped:
        console.print(f"[dim]Skipped {skipped} empty chapters[/]")

    if not chapters:
        raise RuntimeError(
            "No chapters with content were found. "
            "This usually means authentication failed or book access is restricted."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Add CSS
    style_dir = output_dir / "style"
    style_dir.mkdir(exist_ok=True)
    (style_dir / "main.css").write_text(_get_default_css() + NAV_CSS, encoding="utf-8")

    # Add cover image if available
    cover_filename = ""
    if book.cover_image:
        cover_filename = f"cover.{_guess_image_extension(book.cover_image)}"
        (output_dir / cover_filename).write_bytes(book.cover_image)
        console.print("[dim]Added cover image[/]")

    # Add images (chapter HTML already references them as images/<name>)
    written = 0
    for image in book.images.values():
        if image.data:
            image_path = output_dir / image.filename
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image.data)
            written += 1
    if written:
        console.print(f"[dim]Added {written} images[/]")

    # Create chapters
    filenames = [f"{_chapter_basename(c)}.html" for c in chapters]
    # Map O'Reilly's original chapter filenames (e.g. ch02.html) to ours
    link_map = {f"{c.id}.html": f for c, f in zip(chapters, filenames, strict=True)}
    for i, chapter in enumerate(chapters):
        prev_file = filenames[i - 1] if i > 0 else None
        next_file = filenames[i + 1] if i < len(chapters) - 1 else None
        page = _render_chapter(
            book.metadata.title, chapter, link_map, prev_file, next_file
        )
        (output_dir / filenames[i]).write_text(page, encoding="utf-8")
    console.print(f"[dim]Added {len(chapters)} chapters[/]")

    # Create table of contents
    index_path = output_dir / "index.html"
    index_path.write_text(
        _render_index(book, chapters, filenames, cover_filename), encoding="utf-8"
    )
    console.print(f"[bold green]HTML saved to: {output_dir}[/]")

    return index_path


def _render_chapter(
    book_title: str,
    chapter: Chapter,
    link_map: dict[str, str],
    prev_file: str | None,
    next_file: str | None,
) -> str:
    """Render a chapter as a standalone HTML page with navigation."""
    body_content = _rewrite_chapter_links(
        _extract_body_content(chapter.html_content), link_map
    )
    nav = _render_nav(prev_file, next_file)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{_escape_html(chapter.title)} - {_escape_html(book_title)}</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
    {nav}
    <h1>{_escape_html(chapter.title)}</h1>
    {body_content}
    {nav}
</body>
</html>"""


def _rewrite_chapter_links(body_content: str, link_map: dict[str, str]) -> str:
    """Point cross-chapter links (e.g. ch02.html#id329) at the local files."""
    soup = BeautifulSoup(body_content, "html.parser")
    for link in soup.find_all("a", href=True):
        parts = urlsplit(link["href"])
        if parts.netloc and not parts.netloc.endswith("oreilly.com"):
            continue
        target = link_map.get(parts.path.rsplit("/", 1)[-1])
        if target:
            link["href"] = f"{target}#{parts.fragment}" if parts.fragment else target
    return str(soup)


def _render_nav(prev_file: str | None, next_file: str | None) -> str:
    """Render previous / contents / next links."""
    prev_link = f'<a href="{prev_file}">&larr; Previous</a>' if prev_file else "<span></span>"
    next_link = f'<a href="{next_file}">Next &rarr;</a>' if next_file else "<span></span>"
    return (
        f'<nav class="chapter-nav">{prev_link}'
        f'<a href="index.html">Contents</a>{next_link}</nav>'
    )


def _render_index(
    book: Book, chapters: list[Chapter], filenames: list[str], cover_filename: str
) -> str:
    """Render the table of contents page."""
    meta = book.metadata
    cover = (
        f'<img class="cover" src="{cover_filename}" alt="Cover"/>' if cover_filename else ""
    )
    authors = (
        f"<p>{_escape_html(', '.join(meta.authors))}</p>" if meta.authors else ""
    )
    items = "\n".join(
        f'        <li><a href="{filename}">{_escape_html(chapter.title)}</a></li>'
        for chapter, filename in zip(chapters, filenames, strict=True)
    )

    return f"""<!DOCTYPE html>
<html lang="{_escape_html(meta.language)}">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{_escape_html(meta.title)}</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
    {cover}
    <h1>{_escape_html(meta.title)}</h1>
    {authors}
    <h2>Contents</h2>
    <ol>
{items}
    </ol>
</body>
</html>"""
