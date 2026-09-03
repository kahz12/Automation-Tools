"""Every tool screen, and the map from menu label to screen.

Kept as the single import site the rest of the app already used, so
splitting the module changed nothing outside this package.
"""
from automation_tools.cli.screens.base import (
    ConfirmModal, ExecutionScreen, ProviderFieldMixin, ToolScreen, tui_confirm,
)
from automation_tools.cli.screens.files import ArchiverScreen, CleanerScreen, DuplicatesScreen, LogAnalyzerScreen, OrganizerScreen, RenamerScreen, SimilarImagesScreen
from automation_tools.cli.screens.conversion import ConverterScreen, ImageProcessorScreen, PdfConverterScreen, PdfToolkitScreen
from automation_tools.cli.screens.ai import OcrScreen, ReadmeScreen, SummarizerScreen, TranscriberScreen, TranslatorScreen
from automation_tools.cli.screens.web import MonitorScreen, WebClipperScreen, YoutubeScreen
from automation_tools.cli.screens.security import EnvManagerScreen, FileTypeScreen, FlacCheckScreen, IntegrityScreen, MetadataScreen, PasswordScreen, VaultScreen


# ── Screen map: tool label → Screen class ──────────────────────────────────
SCREEN_MAP: dict[str, type[ToolScreen]] = {
    "✂️   Massive Renamer":     RenamerScreen,
    "📦  Organize Downloads":   OrganizerScreen,
    "🧬  Duplicate Detector":   DuplicatesScreen,
    "🧹  Space Cleaner":        CleanerScreen,
    "💾  Archiver":             ArchiverScreen,
    "🔍  Log Analyzer":        LogAnalyzerScreen,
    "🖼️   Image Converter":      ConverterScreen,
    "🪄  Image Processor":      ImageProcessorScreen,
    "📄  Convert to PDF":       PdfConverterScreen,
    "📑  PDF Toolkit":          PdfToolkitScreen,
    "📝  Document Summarizer":  SummarizerScreen,
    "🌐  File Translator":      TranslatorScreen,
    "📘  README Generator":     ReadmeScreen,
    "🔡  Image OCR":            OcrScreen,
    "🎤  A/V Transcriber":      TranscriberScreen,
    "💰  Price Monitor":        MonitorScreen,
    "📺  YouTube Downloader":   YoutubeScreen,
    "📰  Web Clipper":          WebClipperScreen,
    "🔎  Metadata Extractor":   MetadataScreen,
    "🔐  Password Manager":     PasswordScreen,
    "🔒  Encryption Vault":     VaultScreen,
    "🧾  Integrity Checker":    IntegrityScreen,
    "⚙️  Dotenv Manager":      EnvManagerScreen,
    "👯  Similar Photos":       SimilarImagesScreen,
    "🔬  File Type Check":      FileTypeScreen,
    "🎼  FLAC Authenticity":    FlacCheckScreen,
}

__all__ = [
    "SCREEN_MAP",
    "ToolScreen",
    "ProviderFieldMixin",
    "ExecutionScreen",
    "ConfirmModal",
    "tui_confirm",
    "ArchiverScreen",
    "CleanerScreen",
    "ConverterScreen",
    "DuplicatesScreen",
    "EnvManagerScreen",
    "FileTypeScreen",
    "FlacCheckScreen",
    "ImageProcessorScreen",
    "IntegrityScreen",
    "LogAnalyzerScreen",
    "MetadataScreen",
    "MonitorScreen",
    "OcrScreen",
    "OrganizerScreen",
    "PasswordScreen",
    "PdfConverterScreen",
    "PdfToolkitScreen",
    "ReadmeScreen",
    "RenamerScreen",
    "SimilarImagesScreen",
    "SummarizerScreen",
    "TranscriberScreen",
    "TranslatorScreen",
    "VaultScreen",
    "WebClipperScreen",
    "YoutubeScreen",
]
