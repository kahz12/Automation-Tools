"""Inventory of every tool screen's widgets, captured before the shared-chrome
refactor of screens.py.

Regenerate this only when a screen's fields deliberately change, never to
make a failing test pass."""

SCREEN_WIDGETS = {
    'ArchiverScreen': {
        "ids": ['action', 'back-btn', 'create-apply', 'create-exclude', 'create-format', 'create-hidden', 'create-output', 'create-sources', 'error-msg', 'extract-apply', 'extract-archive', 'extract-dest', 'extract-overwrite', 'list-archive', 'rb-create', 'rb-extract', 'rb-list', 'rb-tarbz2', 'rb-targz', 'rb-zip', 'run-btn', 'sec-create', 'sec-extract', 'sec-list'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'CleanerScreen': {
        "ids": ['apply', 'back-btn', 'delete-all', 'dir', 'error-msg', 'export', 'export-path', 'find-junk', 'find-large', 'find-old', 'large-mb', 'old-days', 'run-btn', 'sec-delete-all', 'sec-export', 'sec-large', 'sec-old'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'section-sep', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'ConverterScreen': {
        "ids": ['back-btn', 'dpi', 'error-msg', 'img-fmt', 'mode', 'path', 'pdf-fmt', 'quality', 'rb-img', 'rb-jpg', 'rb-pdf', 'rb-pdf-jpg', 'rb-pdf-png', 'rb-pdf-webp', 'rb-png', 'rb-tiff', 'rb-webp', 'run-btn', 'sec-img', 'sec-pdf-opts', 'sec-quality'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'DuplicatesScreen': {
        "ids": ['back-btn', 'delete', 'dir', 'error-msg', 'excludes', 'export', 'export-path', 'run-btn', 'sec-export'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'EnvManagerScreen': {
        "ids": ['action', 'back-btn', 'error-msg', 'example-path', 'out-path', 'rb-generate', 'rb-scan', 'rb-validate', 'run-btn', 'sec-example-path', 'sec-out-path', 'target-path'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'FileTypeScreen': {
        "ids": ['back-btn', 'error-msg', 'excludes', 'export', 'export-path', 'path', 'recursive', 'run-btn', 'sec-export', 'show-unknown'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'ImageProcessorScreen': {
        "ids": ['back-btn', 'error-msg', 'max-size', 'op', 'out-dir', 'path', 'quality', 'rb-bl', 'rb-br', 'rb-center', 'rb-compress', 'rb-resize', 'rb-tl', 'rb-tr', 'rb-watermark', 'recursive', 'run-btn', 'scale', 'sec-compress', 'sec-resize', 'sec-watermark', 'wm-opacity', 'wm-pos', 'wm-text'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'IntegrityScreen': {
        "ids": ['action', 'algorithm', 'back-btn', 'dir', 'error-msg', 'excludes', 'extra', 'hidden', 'manifest', 'output', 'rb-create', 'rb-md5', 'rb-sha256', 'rb-sha512', 'rb-verify', 'run-btn', 'sec-create', 'sec-verify'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'section-sep', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'LogAnalyzerScreen': {
        "ids": ['back-btn', 'case-sensitive', 'error-msg', 'keywords', 'mode', 'out-path', 'path', 'rb-regex', 'rb-text', 'run-btn'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'tool-body', 'tool-panel'],
    },
    'MetadataScreen': {
        "ids": ['back-btn', 'clean', 'error-msg', 'export', 'export-path', 'filepath', 'run-btn', 'sec-export'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'MonitorScreen': {
        "ids": ['action', 'back-btn', 'error-msg', 'rb-config', 'rb-loop', 'rb-now', 'run-btn'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'tool-body', 'tool-panel'],
    },
    'OcrScreen': {
        "ids": ['api-key', 'api-key-label', 'back-btn', 'error-msg', 'label', 'language', 'markdown', 'out-path', 'path', 'provider', 'recursive', 'run-btn'],
        "classes": ['arrow', 'btn-row', 'down-arrow', 'error-msg', 'field-label', 'tool-body', 'tool-panel', 'up-arrow'],
    },
    'OrganizerScreen': {
        "ids": ['action', 'back-btn', 'error-msg', 'policy', 'rb-list', 'rb-overwrite', 'rb-rename', 'rb-run', 'rb-skip', 'rb-undo', 'run-btn', 'sec-policy'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'PasswordScreen': {
        "ids": ['action', 'add-number', 'add-special', 'back-btn', 'capitalize', 'check-breach', 'check-pwd', 'count-phrase', 'count-pwd', 'error-msg', 'length', 'no-ambiguous', 'num-words', 'rb-phrase', 'rb-secure', 'rb-sep-dash', 'rb-sep-dot', 'rb-sep-space', 'rb-sep-us', 'rb-strength', 'run-btn', 'sec-phrase', 'sec-secure', 'sec-strength', 'sep', 'symbols'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'section-sep', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'PdfConverterScreen': {
        "ids": ['action', 'back-btn', 'doc-input', 'doc-out', 'error-msg', 'img-fit', 'img-inputs', 'img-out', 'merge-inputs', 'merge-out', 'page-size', 'rb-a4', 'rb-document', 'rb-images', 'rb-letter', 'rb-merge', 'run-btn', 'sec-document', 'sec-images', 'sec-merge', 'use-lo'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'section-sep', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'PdfToolkitScreen': {
        "ids": ['back-btn', 'decrypt-input', 'decrypt-out', 'decrypt-pwd', 'encrypt-input', 'encrypt-out', 'encrypt-pwd', 'error-msg', 'extract-input', 'extract-out', 'extract-pages', 'merge-input', 'merge-out', 'op', 'rb-180', 'rb-270', 'rb-90', 'rb-decrypt', 'rb-encrypt', 'rb-extract', 'rb-merge', 'rb-rotate', 'rb-split', 'rotate-angle', 'rotate-input', 'rotate-out', 'rotate-pages', 'run-btn', 'sec-decrypt', 'sec-encrypt', 'sec-extract', 'sec-merge', 'sec-rotate', 'sec-split', 'split-input', 'split-out'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'ReadmeScreen': {
        "ids": ['api-key', 'api-key-label', 'back-btn', 'dir', 'error-msg', 'label', 'provider', 'run-btn'],
        "classes": ['arrow', 'btn-row', 'down-arrow', 'error-msg', 'field-label', 'tool-body', 'tool-panel', 'up-arrow'],
    },
    'RenamerScreen': {
        "ids": ['apply', 'back-btn', 'dir', 'error-msg', 'ext', 'keep-name', 'mode', 'new-text', 'old-text', 'pattern', 'preview', 'rb-fecha', 'rb-patron', 'rb-replace', 'run-btn', 'sec-fecha', 'sec-patron', 'sec-preview', 'sec-replace'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'section-sep', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'SimilarImagesScreen': {
        "ids": ['apply', 'back-btn', 'dir', 'error-msg', 'excludes', 'export', 'export-path', 'recursive', 'run-btn', 'sec-export', 'threshold'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'section-sep', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'SummarizerScreen': {
        "ids": ['api-key', 'api-key-label', 'back-btn', 'error-msg', 'filepath', 'label', 'out-path', 'provider', 'run-btn', 'save', 'sec-outpath'],
        "classes": ['arrow', 'btn-row', 'down-arrow', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel', 'up-arrow'],
    },
    'TranscriberScreen': {
        "ids": ['api-key', 'api-key-label', 'back-btn', 'error-msg', 'filepath', 'label', 'mode', 'out-path', 'provider', 'rb-srt', 'rb-txt', 'run-btn', 'sec-outpath'],
        "classes": ['arrow', 'btn-row', 'down-arrow', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel', 'up-arrow'],
    },
    'TranslatorScreen': {
        "ids": ['api-key', 'api-key-label', 'back-btn', 'error-msg', 'filepath', 'label', 'lang', 'other-lang', 'provider', 'rb-de', 'rb-en', 'rb-es', 'rb-fr', 'rb-other', 'rb-pt', 'run-btn', 'save', 'sec-other'],
        "classes": ['arrow', 'btn-row', 'down-arrow', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel', 'up-arrow'],
    },
    'VaultScreen': {
        "ids": ['action', 'back-btn', 'error-msg', 'out-dir', 'password', 'password2', 'path', 'rb-decrypt', 'rb-encrypt', 'recursive', 'remove', 'run-btn', 'sec-confirm'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'WebClipperScreen': {
        "ids": ['back-btn', 'error-msg', 'fmt', 'images', 'out-path', 'rb-md', 'rb-txt', 'run-btn', 'save', 'sec-img', 'sec-out', 'url'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'sub-section', 'tool-body', 'tool-panel'],
    },
    'YoutubeScreen': {
        "ids": ['back-btn', 'error-msg', 'mode', 'playlist', 'rb-audio', 'rb-video', 'run-btn', 'url'],
        "classes": ['btn-row', 'error-msg', 'field-label', 'tool-body', 'tool-panel'],
    },
}
