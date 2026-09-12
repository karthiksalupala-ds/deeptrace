"""
DeepTrace Engine
================
Pure-Python forensic recovery engine for DVR/NVR disk images.
No web/framework dependencies — testable standalone with pytest.
"""

from .base_parser import BaseVendorParser, FrameRecord
from .registry import VendorRegistry

__all__ = ["BaseVendorParser", "FrameRecord", "VendorRegistry"]
__version__ = "0.1.0"
