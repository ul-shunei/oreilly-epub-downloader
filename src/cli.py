"""Command-line interface for O'Reilly book downloader."""

import re
import sys
from pathlib import Path

import click
from rich.console import Console

from .client import OreillyClient
from .cookie_auth import load_cookies
from .epub import create_epub
from .html_export import create_html

console = Console()


def extract_book_id(book_input: str) -> str:
    """Extract book ID from URL or direct input."""
    url_pattern = r"learning\.oreilly\.com/library/view/[^/]+/(\d+)"
    match = re.search(url_pattern, book_input)
    if match:
        return match.group(1)

    if re.match(r"^\d+$", book_input):
        return book_input

    isbn_match = re.search(r"(\d{10,13})", book_input)
    if isbn_match:
        return isbn_match.group(1)

    return book_input


def sanitize_filename(name: str) -> str:
    """Create a safe filename from book title."""
    safe = re.sub(r'[<>:"/\\|?*]', "", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:100]


@click.command()
@click.argument("book", required=True)
@click.option(
    "-c",
    "--cookies",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to cookies.json file",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output path (defaults to ./downloads/<title>.epub, or ./downloads/<title>/ for html)",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["epub", "html"]),
    default="epub",
    show_default=True,
    help="Output format: a single EPUB file, or a folder of HTML pages",
)
def main(book: str, cookies: Path, output: Path | None, output_format: str) -> None:
    """Download O'Reilly books as EPUB or HTML.

    BOOK can be a book ID or full O'Reilly URL.

    \b
    Examples:
        oreilly-dl 9781098166298 -c cookies.json
        oreilly-dl "https://learning.oreilly.com/library/view/book/9781098166298/" -c cookies.json
        oreilly-dl 9781098166298 -c cookies.json -f html
    """
    book_id = extract_book_id(book)
    console.print(f"[bold]Downloading book:[/] {book_id}")

    try:
        session = load_cookies(cookies)

        with OreillyClient(session) as client:
            book_data = client.get_book(book_id)

        safe_title = sanitize_filename(book_data.metadata.title)

        if output_format == "html":
            output_path = output or Path("downloads") / safe_title
            create_html(book_data, output_path)
        else:
            if output:
                output_path = output if output.suffix == ".epub" else output.with_suffix(".epub")
            else:
                downloads = Path("downloads")
                downloads.mkdir(exist_ok=True)
                output_path = downloads / f"{safe_title}.epub"
            create_epub(book_data, output_path)

        console.print(f"\n[bold green]Done:[/] {output_path}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
