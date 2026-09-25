import logging
import os
import re


class SecretRedactionFilter(logging.Filter):
    _patterns = (
        re.compile(
            r"(?i)(authorization\s*[:=]\s*)(?:Bearer\s+)?[A-Za-z0-9._~+/=-]+"
        ),
        re.compile(r"(?i)((?:api[_-]?key|encrypted_secret)\s*[:=]\s*)([^\s,;]+)"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub(
                lambda match: (
                    f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]"
                ),
                message,
            )
        record.msg = message
        record.args = ()
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    redaction = SecretRedactionFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redaction)
