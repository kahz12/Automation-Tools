"""Screens for the tools that work on files and folders."""
from __future__ import annotations


from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, RadioButton, RadioSet, Static, Switch


from automation_tools.cli.screens.base import ToolScreen


# ── 1. Massive Renamer ─────────────────────────────────────────────────────
class RenamerScreen(ToolScreen):
    TOOL_TITLE = "✂️   Massive Renamer"
    TOOL_DESC = "Rename batches of files using patterns, dates, or text replacement"

    def compose_fields(self) -> ComposeResult:
        yield Label("Directory:", classes="field-label")
        yield Input(placeholder="/path/to/folder", id="dir")
        yield Label("Mode:", classes="field-label")
        with RadioSet(id="mode"):
            yield RadioButton("Pattern  (e.g. photo_{:03d}.jpg)", id="rb-patron", value=True)
            yield RadioButton("Date  (e.g. 2024-01-01_file.jpg)", id="rb-fecha")
            yield RadioButton("Text replacement  (find → replace)", id="rb-replace")
        # Pattern section
        with Vertical(id="sec-patron", classes="sub-section"):
            yield Label("Pattern (use {:03d} for numbering):", classes="field-label")
            yield Input(placeholder="photo_{:03d}", id="pattern")
        # Fecha section
        with Vertical(id="sec-fecha", classes="sub-section"):
            yield Label("Keep original name as suffix?", classes="field-label")
            yield Switch(id="keep-name")
        # Replace section
        with Vertical(id="sec-replace", classes="sub-section"):
            yield Label("Text to find:", classes="field-label")
            yield Input(placeholder="copy of", id="old-text")
            yield Label("Replacement (empty = delete):", classes="field-label")
            yield Input(placeholder="", id="new-text")
        yield Static("[dim #4b5563]── Options ──────────────────────────[/]", classes="section-sep")
        yield Label("Filter by extension (optional, e.g. .jpg):", classes="field-label")
        yield Input(placeholder=".jpg", id="ext")
        yield Label("Apply changes? (off = simulation only)", classes="field-label")
        yield Switch(id="apply", value=False)
        with Vertical(id="sec-preview", classes="sub-section"):
            yield Label("Preview & confirm before applying?", classes="field-label")
            yield Switch(id="preview", value=True)

    def on_mount(self) -> None:
        self.query_one("#sec-fecha").display = False
        self.query_one("#sec-replace").display = False
        self.query_one("#sec-preview").display = False

    @on(RadioSet.Changed, "#mode")
    def _mode_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-patron"
        self.query_one("#sec-patron").display = (rid == "rb-patron")
        self.query_one("#sec-fecha").display = (rid == "rb-fecha")
        self.query_one("#sec-replace").display = (rid == "rb-replace")

    @on(Switch.Changed, "#apply")
    def _apply_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-preview").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import renamer
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        mode_map = {"rb-patron": "patron", "rb-fecha": "fecha", "rb-replace": "reemplazo"}
        mode = mode_map.get(self._rval(self.query_one("#mode", RadioSet)) or "rb-patron", "patron")
        pattern, old_text, new_text, keep = None, None, "", False
        if mode == "patron":
            pattern = self._ival(self.query_one("#pattern", Input)) or None
        elif mode == "fecha":
            keep = self._bval(self.query_one("#keep-name", Switch))
        elif mode == "reemplazo":
            old_text = self._ival(self.query_one("#old-text", Input))
            if not old_text:
                self._err("Text to find is required.")
                return
            new_text = self._ival(self.query_one("#new-text", Input))
        ext = self._ival(self.query_one("#ext", Input)) or None
        apply_changes = self._bval(self.query_one("#apply", Switch))
        preview = self._bval(self.query_one("#preview", Switch)) if apply_changes else False
        await self._run_tool(
            renamer.run_massive_rename,
            directory=directory, mode=mode, apply_changes=apply_changes,
            ext_filter=ext, pattern=pattern, keep_name=keep,
            old_text=old_text, new_text=new_text, preview=preview,
        )


# ── 11. Downloads Organizer ────────────────────────────────────────────────
class OrganizerScreen(ToolScreen):
    TOOL_TITLE = "📦  Organize Downloads"
    TOOL_DESC = "Move files in Downloads into subfolders by type"

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("📦  Organize now", id="rb-run", value=True)
            yield RadioButton("↩️   Undo last organization", id="rb-undo")
            yield RadioButton("🗂️   List history", id="rb-list")
        with Vertical(id="sec-policy", classes="sub-section"):
            yield Label("If file already exists in destination:", classes="field-label")
            with RadioSet(id="policy"):
                yield RadioButton("📝  Rename  (file_1.ext)", id="rb-rename", value=True)
                yield RadioButton("⏭️   Skip", id="rb-skip")
                yield RadioButton("⚠️   Overwrite", id="rb-overwrite")

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        self.query_one("#sec-policy").display = (
            (e.pressed.id if e.pressed else "") == "rb-run"
        )

    async def action_do_run(self) -> None:
        from automation_tools.tools import organizer
        action = self._rval(self.query_one("#action", RadioSet)) or "rb-run"
        if action == "rb-undo":
            await self._run_tool(organizer.undo_last)
        elif action == "rb-list":
            def _list_fn() -> None:
                from automation_tools.core.logger import console
                files = organizer.list_history()
                if not files:
                    console.print("[dim #64748b]No history found.[/]")
                else:
                    console.print(f"[bold #22d3ee]History — {len(files)} entries:[/]")
                    for f in files:
                        console.print(f"  [#a78bfa]•[/] {f}")
            await self._run_tool(_list_fn)
        else:
            policy_map = {"rb-rename": "rename", "rb-skip": "skip", "rb-overwrite": "overwrite"}
            policy = policy_map.get(
                self._rval(self.query_one("#policy", RadioSet)) or "rb-rename", "rename"
            )
            await self._run_tool(organizer.run_download_organizer, collision_policy=policy)


# ── 7. Duplicate Detector ──────────────────────────────────────────────────
class DuplicatesScreen(ToolScreen):
    TOOL_TITLE = "🧬  Duplicate Detector"
    TOOL_DESC = "Find identical files by content (MD5 hash)"

    def compose_fields(self) -> ComposeResult:
        yield Label("Directory to scan:", classes="field-label")
        yield Input(placeholder="/path/to/folder", id="dir")
        yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
        yield Input(placeholder="*.tmp, backup_*", id="excludes")
        yield Label("Export CSV report of duplicates?", classes="field-label")
        yield Switch(id="export", value=False)
        with Vertical(id="sec-export", classes="sub-section"):
            yield Label("CSV output path:", classes="field-label")
            yield Input(placeholder="duplicates.csv", id="export-path")
        yield Label("Auto-delete duplicates (keep one original)?", classes="field-label")
        yield Switch(id="delete", value=False)

    def on_mount(self) -> None:
        self.query_one("#sec-export").display = False

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import duplicate_finder
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        raw_exc = self._ival(self.query_one("#excludes", Input))
        excludes = [p.strip() for p in raw_exc.split(",") if p.strip()] if raw_exc else None
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = self._ival(self.query_one("#export-path", Input)) or "duplicates.csv"
        delete = self._bval(self.query_one("#delete", Switch))
        await self._run_tool(duplicate_finder.run_duplicate_finder,
                             directory=directory, auto_delete=delete,
                             excludes=excludes, export_path=export_path)


# ── 24. Similar Photo Finder ────────────────────────────────────────────────
class SimilarImagesScreen(ToolScreen):
    TOOL_TITLE = "👯  Similar Photos"
    TOOL_DESC = "Find photos that look the same even when the files differ"

    def compose_fields(self) -> ComposeResult:
        yield Label("Directory to scan:", classes="field-label")
        yield Input(placeholder="/storage/emulated/0/DCIM", id="dir")
        yield Label("Similarity threshold (0 = strictest, 10 = loose):", classes="field-label")
        yield Input(placeholder="5", id="threshold")
        yield Label("Recurse into subfolders?", classes="field-label")
        yield Switch(id="recursive", value=True)
        yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
        yield Input(placeholder="*_thumb.jpg, .thumbnails", id="excludes")
        yield Static("[dim #4b5563]── Actions ──────────────────────────[/]", classes="section-sep")
        yield Label("Export CSV report of the groups?", classes="field-label")
        yield Switch(id="export", value=False)
        with Vertical(id="sec-export", classes="sub-section"):
            yield Label("CSV output path:", classes="field-label")
            yield Input(placeholder="similar_images.csv", id="export-path")
        yield Label("Delete the extra copies? (off = simulation only)", classes="field-label")
        yield Switch(id="apply", value=False)

    def on_mount(self) -> None:
        self.query_one("#sec-export").display = False

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import similar_images
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        try:
            threshold = max(0, min(64, int(self._ival(self.query_one("#threshold", Input)) or "5")))
        except ValueError:
            threshold = 5
        raw_exc = self._ival(self.query_one("#excludes", Input))
        excludes = [p.strip() for p in raw_exc.split(",") if p.strip()] if raw_exc else None
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = self._ival(self.query_one("#export-path", Input)) or "similar_images.csv"
        await self._run_tool(
            similar_images.run_similar_images,
            directory=directory,
            threshold=threshold,
            recursive=self._bval(self.query_one("#recursive", Switch)),
            excludes=excludes,
            export_path=export_path,
            apply=self._bval(self.query_one("#apply", Switch)),
        )


# ── 13. Space Cleaner ──────────────────────────────────────────────────────
class CleanerScreen(ToolScreen):
    TOOL_TITLE = "🧹  Space Cleaner"
    TOOL_DESC = "Detect cache, large, and old files (dry-run by default)"

    def compose_fields(self) -> ComposeResult:
        yield Label("Directory to analyze:", classes="field-label")
        yield Input(placeholder="/path/to/folder", id="dir")
        yield Static("[dim #4b5563]── What to detect ───────────────────[/]", classes="section-sep")
        yield Label("Find junk/cache files?", classes="field-label")
        yield Switch(id="find-junk", value=True)
        yield Label("Find large files?", classes="field-label")
        yield Switch(id="find-large", value=True)
        with Vertical(id="sec-large", classes="sub-section"):
            yield Label("Large file threshold (MB):", classes="field-label")
            yield Input(placeholder="100", id="large-mb")
        yield Label("Find old files?", classes="field-label")
        yield Switch(id="find-old", value=True)
        with Vertical(id="sec-old", classes="sub-section"):
            yield Label("Age threshold (days since last modification):", classes="field-label")
            yield Input(placeholder="365", id="old-days")
        yield Static("[dim #4b5563]── Actions ──────────────────────────[/]", classes="section-sep")
        yield Label("Apply deletion? (off = simulation only)", classes="field-label")
        yield Switch(id="apply", value=False)
        with Vertical(id="sec-delete-all", classes="sub-section"):
            yield Label("Include large/old files in deletion?", classes="field-label")
            yield Switch(id="delete-all", value=False)
        yield Label("Export scan report to file?", classes="field-label")
        yield Switch(id="export", value=False)
        with Vertical(id="sec-export", classes="sub-section"):
            yield Label("Output path (.json or .csv):", classes="field-label")
            yield Input(placeholder="cleaning_report.json", id="export-path")

    @on(Switch.Changed, "#find-large")
    def _large_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-large").display = e.value

    @on(Switch.Changed, "#find-old")
    def _old_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-old").display = e.value

    @on(Switch.Changed, "#apply")
    def _apply_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-delete-all").display = e.value

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    def on_mount(self) -> None:
        self.query_one("#sec-delete-all").display = False
        self.query_one("#sec-export").display = False

    async def action_do_run(self) -> None:
        from automation_tools.tools import space_cleaner
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        try:
            large_mb = max(1, int(self._ival(self.query_one("#large-mb", Input)) or "100"))
        except ValueError:
            large_mb = 100
        try:
            old_days = max(1, int(self._ival(self.query_one("#old-days", Input)) or "365"))
        except ValueError:
            old_days = 365
        apply = self._bval(self.query_one("#apply", Switch))
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = (
                self._ival(self.query_one("#export-path", Input)) or "cleaning_report.json"
            )
        await self._run_tool(
            space_cleaner.run_space_cleaner,
            directory=directory,
            large_mb=large_mb,
            old_days=old_days,
            find_junk=self._bval(self.query_one("#find-junk", Switch)),
            find_large=self._bval(self.query_one("#find-large", Switch)),
            find_old=self._bval(self.query_one("#find-old", Switch)),
            apply=apply,
            delete_large_and_old=self._bval(self.query_one("#delete-all", Switch)) if apply else False,
            export_path=export_path,
        )


# ── 18. Archiver ───────────────────────────────────────────────────────────
class ArchiverScreen(ToolScreen):
    TOOL_TITLE = "💾  Archiver"
    TOOL_DESC = "Bundle files into a zip/tar backup, list it, or extract it"

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("📦  Create a backup archive", id="rb-create", value=True)
            yield RadioButton("📋  List an archive's contents", id="rb-list")
            yield RadioButton("📂  Extract an archive", id="rb-extract")

        # Create
        with Vertical(id="sec-create", classes="sub-section"):
            yield Label("Sources — files/folders (comma-separated):", classes="field-label")
            yield Input(placeholder="/path/to/folder, /path/to/file.txt", id="create-sources")
            yield Label("Output archive (optional):", classes="field-label")
            yield Input(placeholder="default: <source>_<timestamp>", id="create-output")
            yield Label("Format:", classes="field-label")
            with RadioSet(id="create-format"):
                yield RadioButton("zip", id="rb-zip", value=True)
                yield RadioButton("tar.gz", id="rb-targz")
                yield RadioButton("tar.bz2", id="rb-tarbz2")
            yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
            yield Input(placeholder="*.log, __pycache__, node_modules", id="create-exclude")
            yield Label("Include hidden dotfiles?", classes="field-label")
            yield Switch(id="create-hidden", value=False)
            yield Label("Apply? (off = preview only)", classes="field-label")
            yield Switch(id="create-apply", value=False)

        # List
        with Vertical(id="sec-list", classes="sub-section"):
            yield Label("Archive to inspect:", classes="field-label")
            yield Input(placeholder="/path/to/backup.zip", id="list-archive")

        # Extract
        with Vertical(id="sec-extract", classes="sub-section"):
            yield Label("Archive to extract:", classes="field-label")
            yield Input(placeholder="/path/to/backup.zip", id="extract-archive")
            yield Label("Destination folder (optional):", classes="field-label")
            yield Input(placeholder="default: archive name", id="extract-dest")
            yield Label("Overwrite existing files?", classes="field-label")
            yield Switch(id="extract-overwrite", value=False)
            yield Label("Apply? (off = preview only)", classes="field-label")
            yield Switch(id="extract-apply", value=False)

    _SECTIONS = ("create", "list", "extract")

    def on_mount(self) -> None:
        for name in self._SECTIONS:
            if name != "create":
                self.query_one(f"#sec-{name}").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-create"
        selected = rid.replace("rb-", "")
        for name in self._SECTIONS:
            self.query_one(f"#sec-{name}").display = (name == selected)

    @staticmethod
    def _split(value: str) -> list:
        return [item.strip() for item in value.split(",") if item.strip()]

    async def action_do_run(self) -> None:
        from automation_tools.tools import archiver
        action = (self._rval(self.query_one("#action", RadioSet)) or "rb-create").replace("rb-", "")

        if action == "create":
            sources = self._split(self._ival(self.query_one("#create-sources", Input)))
            if not sources:
                self._err("At least one source file or folder is required.")
                return
            fmt_map = {"rb-zip": "zip", "rb-targz": "tar.gz", "rb-tarbz2": "tar.bz2"}
            fmt = fmt_map.get(self._rval(self.query_one("#create-format", RadioSet)) or "rb-zip", "zip")
            await self._run_tool(
                archiver.run_archiver,
                action="create",
                sources=sources,
                output=self._ival(self.query_one("#create-output", Input)) or None,
                fmt=fmt,
                exclude=self._split(self._ival(self.query_one("#create-exclude", Input))),
                include_hidden=self._bval(self.query_one("#create-hidden", Switch)),
                apply=self._bval(self.query_one("#create-apply", Switch)),
            )

        elif action == "list":
            archive = self._ival(self.query_one("#list-archive", Input))
            if not archive:
                self._err("Archive path is required.")
                return
            await self._run_tool(archiver.run_archiver, action="list", archive=archive)

        else:  # extract
            archive = self._ival(self.query_one("#extract-archive", Input))
            if not archive:
                self._err("Archive path is required.")
                return
            await self._run_tool(
                archiver.run_archiver,
                action="extract",
                archive=archive,
                dest=self._ival(self.query_one("#extract-dest", Input)) or None,
                overwrite=self._bval(self.query_one("#extract-overwrite", Switch)),
                apply=self._bval(self.query_one("#extract-apply", Switch)),
            )


# ── 22. Log Analyzer ─────────────────────────────────────────────────────────
class LogAnalyzerScreen(ToolScreen):
    TOOL_TITLE = "🔍  Log Analyzer"
    TOOL_DESC = "Scan log files for errors, exceptions or specific patterns"

    def compose_fields(self) -> ComposeResult:
        yield Label("File or Directory path:", classes="field-label")
        yield Input(placeholder="/var/log/ OR /path/to/app.log", id="path")
        yield Label("Keywords (comma separated) or Regex pattern:", classes="field-label")
        yield Input(placeholder="Error, Exception, Fatal", id="keywords")

        yield Label("Search mode:", classes="field-label")
        with RadioSet(id="mode"):
            yield RadioButton("Normal text (comma separated)", id="rb-text", value=True)
            yield RadioButton("Regex pattern", id="rb-regex")

        yield Label("Case Sensitive?", classes="field-label")
        yield Switch(id="case-sensitive", value=False)

        yield Label("Save report to file? (Optional):", classes="field-label")
        yield Input(placeholder="report.txt", id="out-path")

    async def action_do_run(self) -> None:
        from automation_tools.tools import log_analyzer
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return
        keywords = self._ival(self.query_one("#keywords", Input))
        if not keywords:
            self._err("Keywords are required.")
            return
            
        use_regex = self._rval(self.query_one("#mode", RadioSet)) == "rb-regex"
        case_sensitive = self._bval(self.query_one("#case-sensitive", Switch))
        out_path = self._ival(self.query_one("#out-path", Input)) or None
        
        await self._run_tool(
            log_analyzer.run_log_analyzer,
            path=path,
            keywords=keywords,
            use_regex=use_regex,
            ignore_case=not case_sensitive,
            out_path=out_path
        )

