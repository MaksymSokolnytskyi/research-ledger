"""Mask secrets and personal paths before anything reaches the vault.

Failure capture reads raw command output, which can contain API keys, tokens,
connection strings and home-directory paths. Everything captured passes through
:func:`redact` first; the vault is meant to be shared and synced, so the default is
to mask anything that looks like a credential, accepting some false positives.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

MASK = "[REDACTED]"

_PATTERNS: tuple[str, ...] = (
    r"sk-ant-[A-Za-z0-9_\-]{20,}",  # Anthropic
    r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}",  # OpenAI-style
    r"pplx-[A-Za-z0-9]{20,}",  # Perplexity
    r"AIza[0-9A-Za-z_\-]{30,}",  # Google / Gemini
    r"gh[pousr]_[A-Za-z0-9]{30,}",  # GitHub tokens
    r"github_pat_[A-Za-z0-9_]{30,}",
    r"hf_[A-Za-z0-9]{30,}",  # Hugging Face
    r"xox[abpr]-[A-Za-z0-9\-]{10,}",  # Slack
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",  # JWT
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}",
    r"[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s@/]+@",  # credentials in URLs
)
# key=value / "key": "value" where the key names a secret.
_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b[\w.\-]*(?:api[_\-]?key|secret|token|passw(?:or)?d|pwd|auth)[\w.\-]*\b"
    r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;]{4,})"
)


def _home_variants() -> list[str]:
    homes = {str(Path.home())}
    for var in ("USERPROFILE", "HOME"):
        if value := os.environ.get(var):
            homes.add(value)
    variants = set()
    for home in homes:
        variants |= {home, home.replace("\\", "/"), home.replace("/", "\\")}
    return sorted((v for v in variants if len(v) > 3), key=len, reverse=True)


def redact(text: str, extra_patterns: Iterable[str] = ()) -> str:
    """Return ``text`` with credentials masked and the home directory shown as ``~``."""
    for pattern in (*_PATTERNS, *extra_patterns):
        text = re.sub(pattern, MASK, text, flags=re.DOTALL)
    text = _ASSIGNMENT_RE.sub(lambda m: m.group(1) + MASK, text)
    for home in _home_variants():
        text = text.replace(home, "~")
    return text
