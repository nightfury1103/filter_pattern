from __future__ import annotations


TECHNIQUE_CHOICES = ("vcp", "minervini-vcp", "nhathoai", "experimental-ema21-compression")
MINERVINI_VCP_SCAN_SETUPS = ("original-vcp", "vcp-1c", "vcp-2c", "vcp-3c")
NHATHOAI_SETUP_CHOICES = (
    "all",
    "original-vcp",
    "vcp-1c",
    "vcp-2c",
    "vcp-3c",
    "dd",
    "fb",
    "sb",
    "bb",
    "rb",
    "irb",
    "arb",
    "vcp",
    "compression",
)
NHATHOAI_SCAN_SETUPS = ("dd", "fb", "sb", "bb", "rb", "irb", "arb", "vcp", "compression")

MINERVINI_TECHNIQUES = {"vcp", "minervini-vcp", "minervini_vcp"}
EMA21_COMPRESSION_TECHNIQUES = {"experimental-ema21-compression", "ema21-compression"}
NHATHOAI_TECHNIQUES = {"nhathoai", "nhathoat"}


def normalize_technique(value: str | None) -> str:
    normalized = (value or "minervini-vcp").strip().lower()
    if normalized in MINERVINI_TECHNIQUES:
        return "minervini-vcp"
    if normalized in EMA21_COMPRESSION_TECHNIQUES:
        return "experimental-ema21-compression"
    if normalized in NHATHOAI_TECHNIQUES:
        return "nhathoai"
    raise ValueError(
        "unknown technique. Choose one of: "
        + ", ".join(("minervini-vcp", "nhathoai", "experimental-ema21-compression"))
    )


def normalize_setup(value: str | None) -> str:
    normalized = (value or "all").strip().lower().replace("_", "-")
    aliases = {
        "original": "original-vcp",
        "minervini-vcp": "original-vcp",
        "1c": "vcp-1c",
        "2c": "vcp-2c",
        "3c": "vcp-3c",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in NHATHOAI_SETUP_CHOICES:
        raise ValueError("unknown setup. Choose one of: " + ", ".join(NHATHOAI_SETUP_CHOICES))
    return normalized
