from __future__ import annotations

import trafilatura
from bs4 import BeautifulSoup


def extract_html(html: str, url: str) -> tuple[str | None, str | None]:
    """Returns (title, main_text) for an HTML page."""
    title: str | None = None
    try:
        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
    except Exception:
        pass

    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not text:
        try:
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except Exception:
            text = None
    return title, text


def extract_links(html: str, base_url: str) -> list[str]:
    """Pulls candidate navigation + media links out of a page. Deliberately skips
    <link> tags (stylesheets/favicons/canonical) which are noise for crawling."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for tag in soup.find_all("a"):
        href = tag.get("href")
        if href:
            links.append(href)
    for tag in soup.find_all(["source", "video", "audio", "embed", "iframe"]):
        src = tag.get("src")
        if src:
            links.append(src)
    return links
