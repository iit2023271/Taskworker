"""Browser tools: browser_navigate / browser_click / browser_type /
browser_submit / browser_read.

Two backends share one interface and one observation shape:

* PlaywrightBrowser — real Chromium (headless) when Playwright is
  importable AND a chromium executable launches. Screenshots are saved to
  runs/<run_id>/screenshots/.
* HttpBrowser — requests + stdlib HTML parsing. Used when Playwright is
  unavailable; it still follows links, fills and submits forms, and
  downloads PDFs.

Both backends download PDF links found on a page into
runs/<run_id>/downloads/ and report the local path.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from .base import ToolContext, make_obs

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _download_pdf(session, url: str, downloads_dir: Path) -> Path | None:
    """Download a PDF to the run's downloads dir. Returns the local path."""
    name = Path(urlparse(url).path).name or "download.pdf"
    dest = downloads_dir / name
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest
    except Exception:
        return None


def _page_obs(ok: bool, url: str, text: str, links, forms,
              pdfs, screenshot=None) -> dict:
    body = [f"Page: {url}"]
    if text.strip():
        body.append(text.strip())
    if links:
        body.append("Links:")
        for link in links[:40]:
            body.append(f"  - {link['text']} -> {link['href']}")
    if forms:
        body.append("Forms:")
        for form in forms:
            fields = ", ".join(f.get("label") or f.get("name") or "?"
                               for f in form.get("fields", []))
            body.append(f"  - action={form.get('action')} fields: {fields}")
    if pdfs:
        body.append("Downloaded PDFs:")
        for pdf in pdfs:
            body.append(f"  - {pdf}")
    return make_obs(ok, "\n".join(body), screenshot=screenshot,
                    data={"url": url, "links": links, "forms": forms,
                          "pdfs": [str(p) for p in pdfs],
                          "pdf": str(pdfs[0]) if pdfs else None})


# ---------------------------------------------------------------------------
# HTML parsing for the HttpBrowser backend
# ---------------------------------------------------------------------------


class _PageParser(HTMLParser):
    """Extract visible text, links and forms from an HTML page."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.text_parts: list[str] = []
        self.links: list[dict] = []
        self.forms: list[dict] = []
        self._skip = 0            # depth inside script/style
        self._current_link: dict | None = None
        self._current_form: dict | None = None
        self._labels: dict[str, str] = {}   # id -> label text
        self._label_for: str | None = None
        self._in_label = False
        self._label_text = ""
        self._label_wrap: str | None = None  # id of input wrapped by a label

    # -- tags --------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "a" and "href" in attrs:
            self._current_link = {"href": urljoin(self.base_url, attrs["href"]),
                                  "text": ""}
        elif tag == "form":
            self._current_form = {
                "action": urljoin(self.base_url, attrs.get("action", "")),
                "method": (attrs.get("method") or "get").lower(),
                "fields": []}
            self.forms.append(self._current_form)
        elif tag == "label":
            self._in_label = True
            self._label_text = ""
            self._label_for = attrs.get("for")
        elif tag in ("input", "textarea", "select") and self._current_form is not None:
            field = {
                "name": attrs.get("name", ""),
                "id": attrs.get("id", ""),
                "type": attrs.get("type", "text") if tag == "input" else tag,
                "value": attrs.get("value", ""),
                "placeholder": attrs.get("placeholder", ""),
                "label": "",
            }
            if self._in_label and not self._label_for:
                self._label_wrap = field["id"] or field["name"]
            self._current_form["fields"].append(field)
        elif tag in ("h1", "h2", "h3", "p", "li", "tr", "td", "th", "div"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._current_link is not None:
            self._current_link["text"] = re.sub(
                r"\s+", " ", self._current_link["text"]).strip()
            if self._current_link["text"] or self._current_link["href"]:
                self.links.append(self._current_link)
            self._current_link = None
        elif tag == "label":
            self._in_label = False
            label = re.sub(r"\s+", " ", self._label_text).strip()
            if self._label_for:
                self._labels[self._label_for] = label
            elif self._label_wrap:
                self._labels[self._label_wrap] = label
            self._label_for = None
            self._label_wrap = None
        elif tag in ("h1", "h2", "h3", "p", "li", "tr", "div"):
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._current_link is not None:
            self._current_link["text"] += data
        if self._in_label:
            self._label_text += data
        if data.strip():
            self.text_parts.append(data)

    def result(self):
        text = re.sub(r"[ \t]+", " ", "".join(self.text_parts))
        text = re.sub(r"\n\s*\n+", "\n", text).strip()
        for form in self.forms:
            for field in form["fields"]:
                key = field.get("id") or field.get("name")
                if key in self._labels:
                    field["label"] = self._labels[key]
                elif field.get("placeholder"):
                    field["label"] = field["placeholder"]
                elif field.get("name"):
                    field["label"] = field["name"]
        return text, self.links, self.forms


# ---------------------------------------------------------------------------
# HttpBrowser backend (requests + HTML parsing)
# ---------------------------------------------------------------------------


class HttpBrowser:
    """No-Chromium fallback backend. Same methods, same observation shape."""

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.session = requests.Session()
        self.current_url: str | None = None
        self.text = ""
        self.links: list[dict] = []
        self.forms: list[dict] = []
        self.filled: dict[str, str] = {}   # field name -> typed value

    # -- core --------------------------------------------------------------
    def _load(self, url: str) -> dict:
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"could not open {url}: {e}")
        return self._parse(url, resp.text)

    def _parse(self, url: str, html: str) -> dict:
        self.current_url = url
        parser = _PageParser(url)
        parser.feed(html)
        self.text, self.links, self.forms = parser.result()
        self.filled = {}
        pdfs = []
        for link in self.links:
            if _is_pdf_url(link["href"]):
                dest = _download_pdf(self.session, link["href"],
                                     self.ctx.downloads_dir)
                if dest is not None:
                    pdfs.append(dest)
        return _page_obs(True, url, self.text, self.links, self.forms, pdfs)

    def navigate(self, url: str) -> dict:
        return self._load(url)

    def read(self) -> dict:
        if not self.current_url:
            return make_obs(False, "no page open yet")
        return self._load(self.current_url)

    def click(self, text: str) -> dict:
        needle = text.strip().lower()
        for link in self.links:
            if needle in link["text"].lower() or needle in link["href"].lower():
                if _is_pdf_url(link["href"]):
                    dest = _download_pdf(self.session, link["href"],
                                         self.ctx.downloads_dir)
                    if dest is None:
                        return make_obs(False, f"could not download {link['href']}")
                    return make_obs(True, f"Downloaded PDF: {dest}",
                                    data={"url": self.current_url,
                                          "pdf": str(dest), "pdfs": [str(dest)]})
                return self._load(link["href"])
        # maybe it is a submit button
        for form in self.forms:
            for field in form["fields"]:
                if field.get("type") == "submit" and needle in (
                        field.get("value", "") or "").lower():
                    return self.submit()
        return make_obs(False, f"no link or button matching {text!r} on this page")

    def type(self, label: str, text: str) -> dict:
        needle = label.strip().lower()
        for form in self.forms:
            for field in form["fields"]:
                if field.get("type") in ("submit", "hidden"):
                    continue
                hay = " ".join(str(field.get(k, "") or "") for k in
                               ("label", "name", "id", "placeholder")).lower()
                if needle in hay:
                    key = field.get("name") or field.get("id")
                    if not key:
                        continue
                    self.filled[key] = text
                    return make_obs(True,
                                    f"Filled {field.get('label') or key!r} "
                                    f"with {text!r} (not submitted yet).",
                                    data={"url": self.current_url})
        return make_obs(False, f"no form field matching label {label!r} "
                               "on this page")

    def submit(self) -> dict:
        if not self.forms:
            return make_obs(False, "no form on this page to submit")
        form = self.forms[0]
        data = {}
        for field in form["fields"]:
            name = field.get("name")
            if not name or field.get("type") == "submit":
                continue
            data[name] = self.filled.get(name, field.get("value", ""))
        url = form["action"] or self.current_url
        try:
            if form["method"] == "post":
                resp = self.session.post(url, data=data, timeout=30)
            else:
                resp = self.session.get(url, params=data, timeout=30)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"form submit to {url} failed: {e}")
        obs = self._parse(resp.url, resp.text)
        obs["text"] = "Form submitted.\n" + obs["text"]
        return obs

    def close(self) -> None:
        self.session.close()


# ---------------------------------------------------------------------------
# Playwright backend (real Chromium)
# ---------------------------------------------------------------------------


class PlaywrightBrowser:
    """Real browser backend. Raises on construction if Chromium cannot
    start, so the factory can fall back to HttpBrowser."""

    def __init__(self, ctx: ToolContext):
        from playwright.sync_api import sync_playwright
        self.ctx = ctx
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception:
            # Headless-shell build missing (only the full chromium was
            # installed): retry with the full chromium executable.
            exe = _find_full_chromium()
            if exe is None:
                raise
            self._browser = self._pw.chromium.launch(
                headless=True, executable_path=str(exe))
        self._page = self._browser.new_page()
        self._shot_no = 0
        self._session = requests.Session()

    # -- helpers -----------------------------------------------------------
    def _shot(self):
        self._shot_no += 1
        path = self.ctx.screenshots_dir / f"shot_{self._shot_no:02d}.png"
        try:
            self._page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return None

    def _collect(self):
        try:
            text = self._page.inner_text("body")
        except Exception:
            text = ""
        links = []
        try:
            for a in self._page.locator("a").all():
                try:
                    href = a.get_attribute("href") or ""
                    label = (a.inner_text() or "").strip()
                    if href:
                        links.append({"text": re.sub(r"\s+", " ", label),
                                      "href": urljoin(self._page.url, href)})
                except Exception:
                    continue
        except Exception:
            pass
        forms = []
        try:
            for form in self._page.locator("form").all():
                fields = []
                for inp in form.locator("input, textarea, select").all():
                    try:
                        fields.append({
                            "name": inp.get_attribute("name") or "",
                            "id": inp.get_attribute("id") or "",
                            "type": inp.get_attribute("type") or "text",
                            "value": inp.get_attribute("value") or "",
                            "placeholder": inp.get_attribute("placeholder") or "",
                            "label": inp.get_attribute("aria-label") or "",
                        })
                    except Exception:
                        continue
                try:
                    action = form.get_attribute("action") or ""
                except Exception:
                    action = ""
                forms.append({"action": urljoin(self._page.url, action),
                              "method": "post", "fields": fields})
        except Exception:
            pass
        return text, links, forms

    def _pdfs_for(self, links):
        pdfs = []
        for link in links:
            if _is_pdf_url(link["href"]):
                dest = _download_pdf(self._session, link["href"],
                                     self.ctx.downloads_dir)
                if dest is not None:
                    pdfs.append(dest)
        return pdfs

    # -- core --------------------------------------------------------------
    def navigate(self, url: str) -> dict:
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"could not open {url}: {e}")
        text, links, forms = self._collect()
        return _page_obs(True, self._page.url, text, links, forms,
                         self._pdfs_for(links), screenshot=self._shot())

    def read(self) -> dict:
        text, links, forms = self._collect()
        return _page_obs(True, self._page.url, text, links, forms, [],
                         screenshot=self._shot())

    def click(self, text: str) -> dict:
        needle = text.strip().lower()
        try:
            loc = self._page.get_by_role("link", name=re.compile(
                re.escape(text), re.I)).first
            if loc.count() == 0:
                loc = self._page.locator("a, button").filter(
                    has_text=re.compile(re.escape(text), re.I)).first
            href = None
            try:
                href = loc.get_attribute("href")
            except Exception:
                href = None
            if href and _is_pdf_url(urljoin(self._page.url, href)):
                dest = _download_pdf(self._session,
                                     urljoin(self._page.url, href),
                                     self.ctx.downloads_dir)
                if dest is None:
                    return make_obs(False, f"could not download {href}")
                return make_obs(True, f"Downloaded PDF: {dest}",
                                data={"url": self._page.url, "pdf": str(dest),
                                      "pdfs": [str(dest)]})
            loc.click(timeout=10000)
            self._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"could not click {text!r}: {e}")
        text2, links, forms = self._collect()
        return _page_obs(True, self._page.url, text2, links, forms,
                         self._pdfs_for(links), screenshot=self._shot())

    def type(self, label: str, text: str) -> dict:
        try:
            field = self._page.get_by_label(label, exact=False).first
            if field.count() == 0:
                field = self._page.locator(
                    f"input[name*='{label}' i], input[id*='{label}' i], "
                    f"input[placeholder*='{label}' i]").first
            field.fill(text, timeout=10000)
            return make_obs(True, f"Filled {label!r} with {text!r} "
                                  "(not submitted yet).",
                            data={"url": self._page.url})
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"could not fill field {label!r}: {e}")

    def submit(self) -> dict:
        try:
            btn = self._page.locator(
                "button[type='submit'], input[type='submit']").first
            if btn.count() == 0:
                btn = self._page.get_by_role("button", name=re.compile(
                    r"submit|add|save|enter", re.I)).first
            btn.click(timeout=10000)
            self._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"could not submit the form: {e}")
        text, links, forms = self._collect()
        obs = _page_obs(True, self._page.url, text, links, forms,
                        self._pdfs_for(links), screenshot=self._shot())
        obs["text"] = "Form submitted.\n" + obs["text"]
        return obs

    def close(self) -> None:
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass


def _find_full_chromium():
    """Locate a full chromium binary under the Playwright cache (used when
    only the full build, not the headless-shell build, was installed)."""
    import glob
    candidates = sorted(glob.glob(
        str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    return Path(candidates[-1]) if candidates else None


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------


def get_browser(ctx: ToolContext):
    """Return a browser backend, preferring Playwright. The choice is cached
    on the context and reported via ctx.backend."""
    if ctx.browser is not None:
        return ctx.browser
    try:
        ctx.browser = PlaywrightBrowser(ctx)
        ctx.backend = "playwright"
    except Exception:
        ctx.browser = HttpBrowser(ctx)
        ctx.backend = "http"
    return ctx.browser
