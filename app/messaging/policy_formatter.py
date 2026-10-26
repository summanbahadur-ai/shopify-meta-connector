"""Deterministic Shopify policy HTML to readable plain text."""
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit


class _PolicyTextParser(HTMLParser):
    blocks = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = []
        self.lists = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template"}:
            self.blocked.append(tag)
        if self.blocked:
            return
        if tag in self.blocks:
            self.parts.append("\n\n")
        elif tag in {"br", "tr"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" ")
        elif tag in {"ul", "ol"}:
            self.parts.append("\n")
            self.lists.append([tag, 0])
        elif tag == "li":
            marker = "- "
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                marker = str(self.lists[-1][1]) + ". "
            self.parts.append("\n" + marker)
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            try:
                parsed = urlsplit(href)
                safe = (parsed.scheme in {"https", "http"} and bool(parsed.hostname)
                        and not parsed.username and not parsed.password) or parsed.scheme in {"mailto", "tel"}
            except ValueError:
                safe = False
            self.links.append((href if safe and not any(c.isspace() for c in href) else "", len(self.parts)))

    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag in self.blocks:
            self.parts.append("\n\n")
        elif tag in {"ul", "ol"}:
            if self.lists:
                self.lists.pop()
            self.parts.append("\n\n")
        elif tag == "a" and self.links:
            href, start = self.links.pop()
            label = "".join(self.parts[start:]).strip()
            if href and label != href:
                self.parts.append(" (" + href + ")" if label else href)

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def policy_html_to_text(body: str | None) -> str:
    """Preserve policy wording, paragraphs, list markers and safe link targets."""
    parser = _PolicyTextParser()
    parser.feed(body or "")
    parser.close()
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
