import logging
import os
import re


class SecretRedactionFilter(logging.Filter):
    _patterns = (
        re.compile(r"\brgh_[A-Za-z0-9_-]+"),
        re.compile(
            r"(?i)(authorization\s*[:=]\s*)(?:Bearer\s+)?[A-Za-z0-9._~+/=-]+"
        ),
        re.compile(r"(?i)((?:api[_-]?key|encrypted_secret)\s*[:=]\s*)([^\s,;]+)"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    )

    def _redact(self, value: str) -> str:
        for pattern in self._patterns:
            value = pattern.sub(
                lambda match: (
                    f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]"
                ),
                value,
            )
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if isinstance(record.args, dict):
            record.args = {
                key: self._redact(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        elif isinstance(record.args, tuple):
            record.args = tuple(
                self._redact(value) if isinstance(value, str) else value
                for value in record.args
            )
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    redaction = SecretRedactionFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redaction)
    logging.getLogger("uvicorn.access").addFilter(redaction)
