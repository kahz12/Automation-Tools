"""Screens for the tools that deal with secrets, integrity and metadata."""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, RadioButton, RadioSet, Static, Switch


from automation_tools.cli.screens.base import ToolScreen


# ── 10. Metadata Extractor ─────────────────────────────────────────────────
class MetadataScreen(ToolScreen):
    TOOL_TITLE = "🔎  Metadata Extractor"
    TOOL_DESC = "Reveal EXIF data from images and PDF information"

    def compose_fields(self) -> ComposeResult:
        yield Label("File to inspect (PDF, JPG, PNG, …):", classes="field-label")
        yield Input(placeholder="/path/to/file.jpg", id="filepath")
        yield Label("Export metadata to file?", classes="field-label")
        yield Switch(id="export", value=False)
        with Vertical(id="sec-export", classes="sub-section"):
            yield Label("Output path (.json or .csv):", classes="field-label")
            yield Input(placeholder="metadata.json", id="export-path")
        yield Label("Create a copy without EXIF data (images only)?", classes="field-label")
        yield Switch(id="clean", value=False)

    def on_mount(self) -> None:
        self.query_one("#sec-export").display = False

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import metadata
        filepath = self._ival(self.query_one("#filepath", Input))
        if not filepath:
            self._err("File path is required.")
            return
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = self._ival(self.query_one("#export-path", Input)) or "metadata.json"
        clean = self._bval(self.query_one("#clean", Switch))
        await self._run_tool(metadata.run_metadata_extractor,
                             filepath=filepath, export_path=export_path, clean_exif=clean)


# ── 12. Password Manager ───────────────────────────────────────────────────
class PasswordScreen(ToolScreen):
    TOOL_TITLE = "🔐  Password Manager"
    TOOL_DESC = "Generate passwords, passphrases, and evaluate strength"

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("🎲  Generate secure password", id="rb-secure", value=True)
            yield RadioButton("🧠  Generate memorable passphrase", id="rb-phrase")
            yield RadioButton("🛡️   Evaluate password strength", id="rb-strength")
        # Secure password section
        with Vertical(id="sec-secure", classes="sub-section"):
            yield Static("[dim #4b5563]── Secure Password ──────────────────[/]", classes="section-sep")
            yield Label("Length (4–128):", classes="field-label")
            yield Input(placeholder="16", id="length")
            yield Label("Include symbols (!@#$…)?", classes="field-label")
            yield Switch(id="symbols", value=True)
            yield Label("Exclude ambiguous chars (I/l/1, O/0)?", classes="field-label")
            yield Switch(id="no-ambiguous", value=False)
            yield Label("How many to generate?", classes="field-label")
            yield Input(placeholder="5", id="count-pwd")
        # Passphrase section
        with Vertical(id="sec-phrase", classes="sub-section"):
            yield Static("[dim #4b5563]── Passphrase ───────────────────────[/]", classes="section-sep")
            yield Label("Number of words (2–10):", classes="field-label")
            yield Input(placeholder="4", id="num-words")
            yield Label("Word separator:", classes="field-label")
            with RadioSet(id="sep"):
                yield RadioButton("Hyphen  (-)", id="rb-sep-dash", value=True)
                yield RadioButton("Dot  (.)", id="rb-sep-dot")
                yield RadioButton("Underscore  (_)", id="rb-sep-us")
                yield RadioButton("Space", id="rb-sep-space")
            yield Label("Capitalize words?", classes="field-label")
            yield Switch(id="capitalize", value=True)
            yield Label("Add number at end?", classes="field-label")
            yield Switch(id="add-number", value=True)
            yield Label("Add symbol at end?", classes="field-label")
            yield Switch(id="add-special", value=False)
            yield Label("How many to generate?", classes="field-label")
            yield Input(placeholder="5", id="count-phrase")
        # Strength section
        with Vertical(id="sec-strength", classes="sub-section"):
            yield Static("[dim #4b5563]── Strength Check ───────────────────[/]", classes="section-sep")
            yield Label("Password to evaluate:", classes="field-label")
            yield Input(placeholder="••••••••", password=True, id="check-pwd")
            yield Label("Check HaveIBeenPwned? (k-anonymity, secure)", classes="field-label")
            yield Switch(id="check-breach", value=True)

    def on_mount(self) -> None:
        self.query_one("#sec-phrase").display = False
        self.query_one("#sec-strength").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-secure"
        self.query_one("#sec-secure").display = (rid == "rb-secure")
        self.query_one("#sec-phrase").display = (rid == "rb-phrase")
        self.query_one("#sec-strength").display = (rid == "rb-strength")

    async def action_do_run(self) -> None:
        from automation_tools.tools import password_generator
        action = self._rval(self.query_one("#action", RadioSet)) or "rb-secure"

        if action == "rb-secure":
            try:
                length = max(4, min(128, int(self._ival(self.query_one("#length", Input)) or "16")))
            except ValueError:
                length = 16
            try:
                count = max(1, min(20, int(self._ival(self.query_one("#count-pwd", Input)) or "5")))
            except ValueError:
                count = 5
            await self._run_tool(
                password_generator.run_generate_password,
                length=length,
                use_special=self._bval(self.query_one("#symbols", Switch)),
                exclude_ambiguous=self._bval(self.query_one("#no-ambiguous", Switch)),
                count=count,
            )

        elif action == "rb-phrase":
            try:
                num_words = max(2, min(10, int(self._ival(self.query_one("#num-words", Input)) or "4")))
            except ValueError:
                num_words = 4
            sep_map = {
                "rb-sep-dash": "-", "rb-sep-dot": ".", "rb-sep-us": "_", "rb-sep-space": " "
            }
            sep = sep_map.get(self._rval(self.query_one("#sep", RadioSet)) or "rb-sep-dash", "-")
            try:
                count = max(1, min(20, int(self._ival(self.query_one("#count-phrase", Input)) or "5")))
            except ValueError:
                count = 5
            await self._run_tool(
                password_generator.run_generate_passphrase,
                num_words=num_words,
                separator=sep,
                capitalize=self._bval(self.query_one("#capitalize", Switch)),
                add_number=self._bval(self.query_one("#add-number", Switch)),
                add_special=self._bval(self.query_one("#add-special", Switch)),
                count=count,
            )

        else:  # strength
            pwd = self._ival(self.query_one("#check-pwd", Input))
            if not pwd:
                self._err("Enter the password to evaluate.")
                return
            await self._run_tool(
                password_generator.run_evaluate_strength,
                password=pwd,
                check_breach=self._bval(self.query_one("#check-breach", Switch)),
            )


class VaultScreen(ToolScreen):
    TOOL_TITLE = "🔒  Encryption Vault"
    TOOL_DESC = "Encrypt or decrypt files and folders with a password (AES-256)"

    # The weak password the user has already been warned about, so a second RUN
    # press means "yes, that one".
    _weak_ack = ""

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("🔒  Encrypt", id="rb-encrypt", value=True)
            yield RadioButton("🔓  Decrypt", id="rb-decrypt")
        yield Label("File or folder:", classes="field-label")
        yield Input(placeholder="/path/to/file_or_folder", id="path")
        yield Label("Password:", classes="field-label")
        yield Input(placeholder="••••••••", password=True, id="password")
        # Only shown for encryption: confirm to avoid locking yourself out.
        with Vertical(id="sec-confirm", classes="sub-section"):
            yield Label("Confirm password:", classes="field-label")
            yield Input(placeholder="••••••••", password=True, id="password2")
        yield Label("Recurse into subfolders?", classes="field-label")
        yield Switch(id="recursive", value=True)
        yield Label("Delete originals after? (irreversible — asks to confirm)",
                    classes="field-label")
        yield Switch(id="remove", value=False)
        with Vertical(id="sec-shred", classes="sub-section"):
            yield Label("Overwrite the originals before deleting them?",
                        classes="field-label")
            yield Switch(id="shred", value=False)
        yield Label("Output folder (leave empty to write next to each file):",
                    classes="field-label")
        yield Input(placeholder="(optional)", id="out-dir")

    def on_mount(self) -> None:
        self.query_one("#sec-shred").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        is_encrypt = (e.pressed.id if e.pressed else "rb-encrypt") == "rb-encrypt"
        self.query_one("#sec-confirm").display = is_encrypt

    @on(Switch.Changed, "#remove")
    def _remove_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-shred").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import vault

        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return
        password = self.query_one("#password", Input).value
        if not password:
            self._err("Password is required.")
            return

        action = "encrypt" if (self._rval(self.query_one("#action", RadioSet)) or "rb-encrypt") == "rb-encrypt" else "decrypt"
        if action == "encrypt":
            password2 = self.query_one("#password2", Input).value
            if password != password2:
                self._err("Passwords do not match.")
                return
            # Once the files are sealed the password is all that protects them,
            # so say so while it can still be changed. Pressing RUN again with
            # the same one goes ahead; editing it asks again.
            problems = vault.password_problems(password)
            if problems and self._weak_ack != password:
                self._weak_ack = password
                self._err("Weak password: " + ", ".join(problems)
                          + ". Press RUN again to use it anyway.")
                return

        await self._run_tool(
            vault.run_vault,
            path=path,
            action=action,
            password=password,
            output_dir=self._ival(self.query_one("#out-dir", Input)) or None,
            remove_originals=self._bval(self.query_one("#remove", Switch)),
            recursive=self._bval(self.query_one("#recursive", Switch)),
            shred=self._bval(self.query_one("#shred", Switch)),
        )


# ── 20. Integrity Checker ──────────────────────────────────────────────────
class IntegrityScreen(ToolScreen):
    TOOL_TITLE = "🧾  Integrity Checker"
    TOOL_DESC = "Create a checksum manifest of a folder and verify it later"

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("🧾  Create a checksum manifest", id="rb-create", value=True)
            yield RadioButton("✅  Verify a folder against a manifest", id="rb-verify")
        yield Label("Directory:", classes="field-label")
        yield Input(placeholder="/path/to/folder", id="dir")

        # Create
        with Vertical(id="sec-create", classes="sub-section"):
            yield Label("Hash algorithm:", classes="field-label")
            with RadioSet(id="algorithm"):
                yield RadioButton("SHA-256  (recommended)", id="rb-sha256", value=True)
                yield RadioButton("SHA-512", id="rb-sha512")
                yield RadioButton("MD5  (fast, legacy)", id="rb-md5")
            yield Label("Manifest output path (optional):", classes="field-label")
            yield Input(placeholder="default: <directory>/checksums.sha256", id="output")

        # Verify
        with Vertical(id="sec-verify", classes="sub-section"):
            yield Label("Manifest file (optional — auto-detects checksums.*):", classes="field-label")
            yield Input(placeholder="default: auto-detect inside the folder", id="manifest")
            yield Label("Also report new files not in the manifest?", classes="field-label")
            yield Switch(id="extra", value=True)

        yield Static("[dim #4b5563]── Options ──────────────────────────[/]", classes="section-sep")
        yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
        yield Input(placeholder="*.log, __pycache__", id="excludes")
        yield Label("Include hidden dotfiles?", classes="field-label")
        yield Switch(id="hidden", value=False)

    def on_mount(self) -> None:
        self.query_one("#sec-verify").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        is_create = (e.pressed.id if e.pressed else "rb-create") == "rb-create"
        self.query_one("#sec-create").display = is_create
        self.query_one("#sec-verify").display = not is_create

    async def action_do_run(self) -> None:
        from automation_tools.tools import integrity
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        raw_exc = self._ival(self.query_one("#excludes", Input))
        excludes = [p.strip() for p in raw_exc.split(",") if p.strip()] if raw_exc else None
        include_hidden = self._bval(self.query_one("#hidden", Switch))
        action = (self._rval(self.query_one("#action", RadioSet)) or "rb-create").replace("rb-", "")

        if action == "create":
            alg_map = {"rb-sha256": "sha256", "rb-sha512": "sha512", "rb-md5": "md5"}
            algorithm = alg_map.get(
                self._rval(self.query_one("#algorithm", RadioSet)) or "rb-sha256", "sha256"
            )
            await self._run_tool(
                integrity.run_integrity,
                action="create",
                directory=directory,
                output=self._ival(self.query_one("#output", Input)) or None,
                algorithm=algorithm,
                exclude=excludes,
                include_hidden=include_hidden,
            )
        else:  # verify
            await self._run_tool(
                integrity.run_integrity,
                action="verify",
                directory=directory,
                manifest=self._ival(self.query_one("#manifest", Input)) or None,
                exclude=excludes,
                include_hidden=include_hidden,
                check_extra=self._bval(self.query_one("#extra", Switch)),
            )

# ── 23. Dotenv & Config Manager ──────────────────────────────────────────────
class EnvManagerScreen(ToolScreen):
    TOOL_TITLE = "⚙️  Dotenv Manager"
    TOOL_DESC = "Manage, scan, and validate your .env files"

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("Generate .env.example template", id="rb-generate", value=True)
            yield RadioButton("Scan directory for exposed .env files", id="rb-scan")
            yield RadioButton("Validate .env against template", id="rb-validate")

        yield Label("Target Path (.env file or directory):", classes="field-label")
        yield Input(placeholder="/path/to/.env OR /path/to/project/", id="target-path")

        with Vertical(id="sec-example-path", classes="sub-section"):
            yield Label("Template Path (e.g. .env.example) [For Validate]:", classes="field-label")
            yield Input(placeholder="/path/to/.env.example", id="example-path")

        with Vertical(id="sec-out-path", classes="sub-section"):
            yield Label("Output Path [For Generate]:", classes="field-label")
            yield Input(placeholder="Leave empty for <target>.example", id="out-path")

    def on_mount(self) -> None:
        self.query_one("#sec-example-path").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-generate"
        self.query_one("#sec-example-path").display = (rid == "rb-validate")
        self.query_one("#sec-out-path").display = (rid == "rb-generate")

    async def action_do_run(self) -> None:
        from automation_tools.tools import env_manager
        
        target_path = self._ival(self.query_one("#target-path", Input))
        if not target_path:
            self._err("Target path is required.")
            return
            
        action_map = {"rb-generate": "generate", "rb-scan": "scan", "rb-validate": "validate"}
        action = action_map.get(self._rval(self.query_one("#action", RadioSet)) or "rb-generate")
        
        example_path = self._ival(self.query_one("#example-path", Input)) or None
        out_path = self._ival(self.query_one("#out-path", Input)) or None
        
        await self._run_tool(
            env_manager.run_env_manager,
            action=action,
            target_path=target_path,
            example_path=example_path,
            out_path=out_path
        )



# ── 25. File Type Verifier ──────────────────────────────────────────────────
class FileTypeScreen(ToolScreen):
    TOOL_TITLE = "🔬  File Type Check"
    TOOL_DESC = "Check that files really are what their extension claims"

    def compose_fields(self) -> ComposeResult:
        yield Label("File or directory to check:", classes="field-label")
        yield Input(placeholder="/path/to/folder", id="path")
        yield Label("Recurse into subfolders?", classes="field-label")
        yield Switch(id="recursive", value=True)
        yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
        yield Input(placeholder="*.tmp, node_modules", id="excludes")
        yield Label("Also list files with no known signature?", classes="field-label")
        yield Switch(id="show-unknown", value=False)
        yield Label("Export CSV report?", classes="field-label")
        yield Switch(id="export", value=False)
        with Vertical(id="sec-export", classes="sub-section"):
            yield Label("CSV output path:", classes="field-label")
            yield Input(placeholder="file_types.csv", id="export-path")

    def on_mount(self) -> None:
        self.query_one("#sec-export").display = False

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import file_type
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("A file or directory is required.")
            return
        raw_exc = self._ival(self.query_one("#excludes", Input))
        excludes = [p.strip() for p in raw_exc.split(",") if p.strip()] if raw_exc else None
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = self._ival(self.query_one("#export-path", Input)) or "file_types.csv"
        await self._run_tool(
            file_type.run_file_type_check,
            path=path,
            recursive=self._bval(self.query_one("#recursive", Switch)),
            excludes=excludes,
            export_path=export_path,
            show_unknown=self._bval(self.query_one("#show-unknown", Switch)),
        )



# ── 26. FLAC Authenticity ────────────────────────────────────────────────────
class FlacCheckScreen(ToolScreen):
    TOOL_TITLE = "🎼  FLAC Authenticity"
    TOOL_DESC = "Check whether .flac files really hold lossless audio"

    def compose_fields(self) -> ComposeResult:
        yield Label("FLAC file or music folder:", classes="field-label")
        yield Input(placeholder="/path/to/music", id="path")
        yield Label("Recurse into subfolders?", classes="field-label")
        yield Switch(id="recursive", value=True)
        yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
        yield Input(placeholder="*.tmp, samples", id="excludes")
        yield Label("Verify the stored checksum? (slower: decodes every file)",
                    classes="field-label")
        yield Switch(id="check-md5", value=True)
        yield Label("Also list the files that passed?", classes="field-label")
        yield Switch(id="show-all", value=False)
        yield Label("Render a spectrogram per file?", classes="field-label")
        yield Switch(id="spectrograms", value=False)
        with Vertical(id="sec-spectrograms", classes="sub-section"):
            yield Label("Folder for the PNG files:", classes="field-label")
            yield Input(placeholder="spectrograms", id="spectrograms-dir")
        yield Label("Export CSV report?", classes="field-label")
        yield Switch(id="export", value=False)
        with Vertical(id="sec-export", classes="sub-section"):
            yield Label("CSV output path:", classes="field-label")
            yield Input(placeholder="flac_report.csv", id="export-path")

    def on_mount(self) -> None:
        self.query_one("#sec-spectrograms").display = False
        self.query_one("#sec-export").display = False

    @on(Switch.Changed, "#spectrograms")
    def _spectrograms_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-spectrograms").display = e.value

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import flac_check
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("A FLAC file or folder is required.")
            return
        raw_exc = self._ival(self.query_one("#excludes", Input))
        excludes = [p.strip() for p in raw_exc.split(",") if p.strip()] if raw_exc else None
        spectrogram_dir = None
        if self._bval(self.query_one("#spectrograms", Switch)):
            spectrogram_dir = self._ival(
                self.query_one("#spectrograms-dir", Input)) or "spectrograms"
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = self._ival(self.query_one("#export-path", Input)) or "flac_report.csv"
        await self._run_tool(
            flac_check.run_flac_check,
            path=path,
            recursive=self._bval(self.query_one("#recursive", Switch)),
            excludes=excludes,
            export_path=export_path,
            spectrogram_dir=spectrogram_dir,
            check_md5=self._bval(self.query_one("#check-md5", Switch)),
            show_all=self._bval(self.query_one("#show-all", Switch)),
        )
