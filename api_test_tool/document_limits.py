"""Document limits shared by web, storage and CLI (decimal MB)."""
MAX_DOCUMENT_BYTES = 50_000_000
DOCUMENT_LIMIT_LABEL = "50 MB"
# JSON can encode one byte as six characters (e.g. \u0000).
# Leave room for metadata; document content is checked after JSON decoding.
MAX_DOCUMENT_REQUEST_BYTES = 6 * MAX_DOCUMENT_BYTES + 1_500_000
