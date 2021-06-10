"""
Entrypoint
"""
import os
import re
from pathlib import Path
from typing import List, Optional, Pattern

import requests
import typer
import urllib3

from urllib3.exceptions import InsecureRequestWarning

from bookstack_markdown_export import dao
from bookstack_markdown_export.dao import PageDetails

LOWEST_HEADER_LEVEL = 8

# language=RegExp
IMAGE_LINK_REGEX_TEMPLATE = r"\[\!\[.+\]\(__BASE_URL__/uploads/.*?\.\w{3}\)\]\((__BASE_URL__/uploads/.*?/([^/]*?\.\w{3}))\)"
# language=RegExp
INTERNAL_LINK_REGEX_TEMPLATE = r"__BASE_URL__/books/(.+?)/page/(.+?)\)"


urllib3.disable_warnings(category=InsecureRequestWarning)


def header_re(level: int) -> Pattern[str]:
    return re.compile("^" + header_text(level), flags=re.MULTILINE)


def header_text(level: int) -> str:
    return "#" * level + " "


def get_top_level_header(md: str) -> Optional[int]:
    for level in range(1, LOWEST_HEADER_LEVEL):
        if header_re(level).search(md) is not None:
            return level

    return None


def export_doc(export_path: Path, doc: PageDetails, image_link_regex: Pattern, internal_link_regex: Pattern) -> bool:
    """Modifies and exports markdown. Returns true if e.g. internal links were found and manual intervention is required"""
    # path encodes shelf + book in hierarchy
    path_to_book = export_path / doc.shelf / doc.book
    os.makedirs(path_to_book, exist_ok=True)

    # Download any embedded images and replace the image embed MD
    # we do it reversed so that modifying the markdown doesn't make all the indexes off
    for match in reversed(tuple(image_link_regex.finditer(doc.page_markdown))):
        image_url = match.group(1)
        image_filename = match.group(2)

        typer.echo(typer.style(f"Found embedded image in {doc.book} => {doc.page_title}: {image_filename}", fg=typer.colors.BLUE))

        # download image to same dir as page will go
        response = requests.get(image_url, verify=False)
        response.raise_for_status()

        with open(path_to_book / image_filename, "wb") as f:
            f.write(response.content)

        # replace markdown
        doc.page_markdown = doc.page_markdown[: match.start()] + f"![]({image_filename})" + doc.page_markdown[match.end() + 1 :]

    # Decrease header level to make sure top level is #. (Lots of pages have a top level of ## because # was too large.)
    original_top_level = get_top_level_header(doc.page_markdown)
    if original_top_level is not None and original_top_level != 1:
        # List of tuples like (^##, #), (^###, ##), etc (if ## was the original top level header) for find/replace with re
        replacements = [(header_re(x), header_text(x - original_top_level + 1)) for x in range(original_top_level, LOWEST_HEADER_LEVEL)]

        for find_re, replacement in replacements:
            doc.page_markdown = find_re.sub(replacement, doc.page_markdown)

    # Add page title as H1
    doc.page_markdown = f"# {'DRAFT: ' if doc.draft else ''}{doc.page_title}\n\n" + doc.page_markdown

    # Find any linked pages and print them out
    internal_links_found = False
    for internal_link in internal_link_regex.finditer(doc.page_markdown):
        internal_links_found = True
        typer.echo(
            typer.style(
                f">> Internal link found in [{doc.page_title}] to [{internal_link.group(1)}]/[{internal_link.group(2)}]",
                fg=typer.colors.BRIGHT_MAGENTA,
            )
        )

        snippet = doc.page_markdown[internal_link.start() - 60 : internal_link.start()]
        for line_num, snippet_line in enumerate(snippet.splitlines()):
            typer.echo("    " + snippet_line)

    # sanitize filename and save
    safe_page_title = doc.page_title.replace("/", "-")
    with open(path_to_book / f"{safe_page_title}.md", "w") as f:
        f.write(doc.page_markdown)

    return internal_links_found


def main(
    mysql_host: str = typer.Option(..., prompt=True),
    mysql_user: str = typer.Option(..., prompt=True),
    mysql_pass: str = typer.Option(..., prompt=True, confirmation_prompt=True, hide_input=True),
    mysql_db: str = typer.Option("bookstack"),
    mysql_port: int = typer.Option(3306),
    bookstack_url_root: str = typer.Option(..., prompt=True),
    export_path: Path = typer.Option(Path("export")),
):
    # Drop trailing slash, if it exists, on url, and substitute into regex templates
    bookstack_url_root = bookstack_url_root.rstrip("/")
    image_link_regex = re.compile(IMAGE_LINK_REGEX_TEMPLATE.replace("__BASE_URL__", bookstack_url_root))
    internal_link_regex = re.compile(INTERNAL_LINK_REGEX_TEMPLATE.replace("__BASE_URL__", bookstack_url_root))

    # Get MD directly from DB
    typer.echo(typer.style("> Connecting to DB", fg=typer.colors.GREEN))
    conn = dao.connection(mysql_host, mysql_port, mysql_user, mysql_pass, mysql_db)

    typer.echo(typer.style("> Retrieving all documents from db", fg=typer.colors.GREEN))
    documents: List[PageDetails] = dao.get_all_pages(conn)

    # Export all the markdown as files, making modifications as needed
    typer.echo(typer.style("> Exporting all documents as markdown", fg=typer.colors.GREEN))
    manual_required = False
    with typer.progressbar(documents) as bar:
        doc: PageDetails
        for doc in bar:
            manual_required = export_doc(export_path, doc, image_link_regex, internal_link_regex) or manual_required

    if manual_required:
        typer.echo(
            typer.style("Manual cleanup required. See '>>' messages above.", fg=typer.colors.BRIGHT_YELLOW, bg=typer.colors.BLACK, bold=True)
        )


if __name__ == "__main__":
    typer.run(main)
