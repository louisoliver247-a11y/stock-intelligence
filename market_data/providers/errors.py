class ProviderError(RuntimeError):
    """Sanitized provider failure, independent of broker payloads and transport URLs."""

    def __init__(self, code: str, status: int | None = None):
        super().__init__(code)
        self.code = code
        self.status = status
