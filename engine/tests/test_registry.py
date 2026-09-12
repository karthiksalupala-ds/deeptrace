"""
tests/test_registry.py — VendorRegistry and detection tests.

All tests use synthetic disk images — no real hardware required.
"""

import datetime
import os
import tempfile

import pytest

from engine.registry import build_default_registry
from engine.synthetic_image_gen import SyntheticImageGenerator


@pytest.fixture
def tmp_img(tmp_path):
    """Helper: write a generator's bytes to a temp file and return path."""
    def _write(gen: SyntheticImageGenerator) -> str:
        p = str(tmp_path / "test.img")
        gen.write(p)
        return p
    return _write


def _hik_image(tmp_path) -> str:
    gen = SyntheticImageGenerator()
    gen.add_manufacturer_signature("hikvision")
    path = str(tmp_path / "hik.img")
    gen.write(path)
    return path


def _dahua_image(tmp_path) -> str:
    gen = SyntheticImageGenerator()
    gen.add_manufacturer_signature("dahua")
    path = str(tmp_path / "dahua.img")
    gen.write(path)
    return path


def _unknown_image(tmp_path) -> str:
    gen = SyntheticImageGenerator()
    gen.add_noise(4096)
    path = str(tmp_path / "unknown.img")
    gen.write(path)
    return path


def _stub_vendor_image(vendor_id: str, tmp_path) -> str:
    gen = SyntheticImageGenerator()
    gen.add_manufacturer_signature(vendor_id)
    path = str(tmp_path / f"{vendor_id}.img")
    gen.write(path)
    return path


class TestVendorRegistry:

    def test_detects_hikvision(self, tmp_path):
        registry = build_default_registry()
        img = _hik_image(tmp_path)
        parser, offset = registry.detect_vendor(img)
        assert parser is not None
        assert parser.vendor_id == "hikvision"
        assert offset is not None

    def test_detects_dahua(self, tmp_path):
        registry = build_default_registry()
        img = _dahua_image(tmp_path)
        parser, offset = registry.detect_vendor(img)
        assert parser is not None
        assert parser.vendor_id == "dahua"
        assert offset is not None

    def test_returns_none_for_unknown(self, tmp_path):
        registry = build_default_registry()
        img = _unknown_image(tmp_path)
        parser, offset = registry.detect_vendor(img)
        assert parser is None
        assert offset is None

    def test_list_vendors_returns_all_eight(self):
        registry = build_default_registry()
        vendors = registry.list_vendors()
        vendor_ids = {v["vendor_id"] for v in vendors}
        expected = {"hikvision", "dahua", "cpplus", "godrej",
                    "uniview", "honeywell", "tplink", "matrix"}
        assert vendor_ids == expected

    def test_fully_implemented_flags(self):
        registry = build_default_registry()
        vendors = registry.list_vendors()
        impl_map = {v["vendor_id"]: v["is_fully_implemented"] for v in vendors}
        assert impl_map["hikvision"] is True
        assert impl_map["dahua"] is True
        assert impl_map["cpplus"] is True
        assert impl_map["godrej"] is True
        assert impl_map["uniview"] is False
        assert impl_map["honeywell"] is False
        assert impl_map["tplink"] is False
        assert impl_map["matrix"] is False

    @pytest.mark.parametrize("vendor_id", ["uniview", "honeywell", "tplink", "matrix"])
    def test_stub_vendors_detect_their_own_image(self, vendor_id, tmp_path):
        """Stub vendors should detect() images containing their own OEM marker."""
        registry = build_default_registry()
        img = _stub_vendor_image(vendor_id, tmp_path)
        parser, offset = registry.detect_vendor(img)
        # These vendors have lower priority — we look for them specifically
        from engine.registry import VendorRegistry
        from engine.vendors.uniview import UniviewParser
        from engine.vendors.honeywell import HoneywellParser
        from engine.vendors.tplink import TpLinkParser
        from engine.vendors.matrix import MatrixParser
        stub_map = {
            "uniview": UniviewParser,
            "honeywell": HoneywellParser,
            "tplink": TpLinkParser,
            "matrix": MatrixParser,
        }
        cls = stub_map[vendor_id]
        instance = cls()
        found, sig_offset = instance.detect(img)
        assert found is True, f"{vendor_id} should detect its own marker"

    @pytest.mark.parametrize("vendor_id", ["uniview", "honeywell", "tplink", "matrix"])
    def test_stub_vendors_raise_not_implemented(self, vendor_id, tmp_path):
        """Stubs must raise NotImplementedError from parse_frames()."""
        img = _stub_vendor_image(vendor_id, tmp_path)
        from engine.vendors.uniview import UniviewParser
        from engine.vendors.honeywell import HoneywellParser
        from engine.vendors.tplink import TpLinkParser
        from engine.vendors.matrix import MatrixParser
        stub_map = {
            "uniview": UniviewParser,
            "honeywell": HoneywellParser,
            "tplink": TpLinkParser,
            "matrix": MatrixParser,
        }
        parser = stub_map[vendor_id]()
        with pytest.raises(NotImplementedError):
            parser.parse_frames(img)
