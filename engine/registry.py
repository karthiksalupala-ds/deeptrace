"""
registry.py — VendorRegistry: discovers the correct parser for a disk image.

Registration order matters: Hikvision and Dahua are registered first since
they represent ~38% of the global market and are the most common formats.
All other vendors are registered after them.

Usage:
    registry = VendorRegistry()
    parser = registry.detect_vendor("path/to/image.img")
    if parser:
        frames = parser.parse_frames("path/to/image.img")
"""

from __future__ import annotations

import logging
from typing import Optional

from .base_parser import BaseVendorParser, DetectionResult

logger = logging.getLogger(__name__)


class VendorRegistry:
    """
    Iterates all registered vendor parsers in priority order and returns
    the first one whose detect() returns True for the given disk image.
    """

    def __init__(self) -> None:
        self._parsers: list[BaseVendorParser] = []

    def register(self, parser: BaseVendorParser) -> None:
        """Register a vendor parser. Call order determines priority."""
        self._parsers.append(parser)
        logger.debug("Registered vendor parser: %s", parser.vendor_id)

    def list_vendors(self) -> list[dict]:
        """Return metadata for all registered vendors (for API/UI)."""
        return [
            {
                "id": p.vendor_id,
                "vendor_id": p.vendor_id,
                "vendor_name": p.vendor_name,
                "vendor_description": p.vendor_description,
                "is_fully_implemented": p.is_fully_implemented(),
            }
            for p in self._parsers
        ]

    def detect_vendor(
        self, image_path: str
    ) -> tuple[Optional[BaseVendorParser], Optional[int]]:
        """
        Try each registered parser's detect() in priority order.

        Returns:
            (parser, offset) if a vendor signature was found, else (None, None).
        """
        for parser in self._parsers:
            try:
                found, offset = parser.detect(image_path)
                if found:
                    logger.info(
                        "Detected vendor '%s' at offset %s in %s",
                        parser.vendor_id,
                        offset,
                        image_path,
                    )
                    return parser, offset
            except Exception as exc:
                logger.warning(
                    "Parser '%s' raised during detect(): %s", parser.vendor_id, exc
                )
        logger.info("No vendor signature found in %s", image_path)
        return None, None

    def detect_vendor_verbose(
        self, image_path: str, max_scan_bytes: int = 16 * 1024 * 1024
    ) -> tuple[Optional[BaseVendorParser], DetectionResult]:
        """Detect using fixed offsets first, then bounded signature scanning."""
        for parser in self._parsers:
            try:
                result = parser.detect_verbose(image_path, max_scan_bytes=max_scan_bytes)
                if result.found:
                    logger.info("Detected vendor '%s' via %s at offset %s", parser.vendor_id, result.method, result.offset)
                    return parser, result
            except Exception as exc:
                logger.warning("Parser '%s' raised during verbose detect: %s", parser.vendor_id, exc)
        return None, DetectionResult(False, None, "not_found", "")


def build_default_registry() -> VendorRegistry:
    """
    Build and return the default registry with all vendor parsers
    registered in priority order.
    """
    # Import here to avoid circular imports
    from .vendors.hikvision import HikvisionParser
    from .vendors.dahua import DahuaParser
    from .vendors.cpplus import CpPlusParser
    from .vendors.godrej import GodrejParser
    from .vendors.uniview import UniviewParser
    from .vendors.honeywell import HoneywellParser
    from .vendors.tplink import TpLinkParser
    from .vendors.matrix import MatrixParser

    registry = VendorRegistry()
    # Full implementations first (highest market share)
    registry.register(HikvisionParser())
    registry.register(DahuaParser())
    # Delegation parsers (confirmed OEM relationships)
    registry.register(CpPlusParser())
    registry.register(GodrejParser())
    # Detection-only stubs (independent or unresearched file systems)
    registry.register(UniviewParser())
    registry.register(HoneywellParser())
    registry.register(TpLinkParser())
    registry.register(MatrixParser())
    return registry
