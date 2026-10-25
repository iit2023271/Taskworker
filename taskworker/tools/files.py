"""File tools: read_file (PDF via pypdf, text formats as text) and list_dir.
"""

from __future__ import annotations

from pathlib import Path

from .base import Tool, make_obs

TEXT_SUFFIXES = {".txt", ".csv", ".json", ".md", ".html", ".log"}


class ReadFileTool(Tool):
    name = "read_file"
    description = ("Read a file. PDFs are converted to text with pypdf; "
                   ".txt/.csv/.json/.md/.html files are read as text.")
    args_schema = {
        "type": "object",
        "properties": {"path": {"type": "string",
                                "description": "Path to the file to read."}},
        "required": ["path"],
    }

    def run(self, args: dict, ctx) -> dict:
        path = Path(str(args.get("path", ""))).expanduser()
        if not path.exists():
            return make_obs(False, f"file not found: {path}")
        try:
            if path.suffix.lower() == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                pages = []
                for page in reader.pages:
                    pages.append(page.extract_text() or "")
                text = "\n".join(pages)
                return make_obs(True, f"PDF {path} ({len(reader.pages)} pages):\n{text}",
                                data={"path": str(path), "pages": len(reader.pages)})
            if path.suffix.lower() in TEXT_SUFFIXES or path.suffix == "":
                text = path.read_text(encoding="utf-8", errors="replace")
                return make_obs(True, f"File {path}:\n{text}",
                                data={"path": str(path)})
            return make_obs(False, f"unsupported file type: {path.suffix} ({path})")
        except Exception as e:  # noqa: BLE001 - surfaced as a failed observation
            return make_obs(False, f"could not read {path}: {e}")


class ListDirTool(Tool):
    name = "list_dir"
    description = "List the files in a directory."
    args_schema = {
        "type": "object",
        "properties": {"path": {"type": "string",
                                "description": "Directory to list."}},
        "required": ["path"],
    }

    def run(self, args: dict, ctx) -> dict:
        path = Path(str(args.get("path", ""))).expanduser()
        if not path.is_dir():
            return make_obs(False, f"not a directory: {path}")
        try:
            entries = sorted(p.name for p in path.iterdir())
            lines = "\n".join(entries) if entries else "(empty)"
            return make_obs(True, f"Contents of {path}:\n{lines}",
                            data={"path": str(path), "entries": entries})
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"could not list {path}: {e}")
