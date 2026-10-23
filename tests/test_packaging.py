"""Check that HACS's integration-only download includes the card and its route."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components/bosch_local"


class HacsPackagingTests(unittest.IsolatedAsyncioTestCase):
    async def test_bundled_card_route_uses_installed_file(self):
        # Simulate a HACS install: import only the integration directory.
        http = ModuleType("homeassistant.components.http")
        http.StaticPathConfig = lambda url, path, cache: SimpleNamespace(
            url_path=url, path=path, cache_headers=cache)
        coordinator = ModuleType("bosch_package_test.coordinator")
        coordinator.Dishwasher = object
        spec = importlib.util.spec_from_file_location(
            "bosch_package_test", INTEGRATION / "__init__.py",
            submodule_search_locations=[str(INTEGRATION)])
        module = importlib.util.module_from_spec(spec)
        stubs = {"bosch_package_test": module, "bosch_package_test.coordinator": coordinator,
                 "homeassistant": ModuleType("homeassistant"),
                 "homeassistant.components": ModuleType("homeassistant.components"),
                 "homeassistant.components.http": http}
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)
        hass = SimpleNamespace(http=SimpleNamespace(async_register_static_paths=AsyncMock()))
        self.assertTrue(await module.async_setup(hass, {}))
        routes = hass.http.async_register_static_paths.await_args.args[0]
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].url_path, "/bosch_local/bosch-local-card.js")
        self.assertEqual(Path(routes[0].path), INTEGRATION / "frontend/bosch-local-card.js")
        self.assertTrue(Path(routes[0].path).is_file())
        self.assertFalse(routes[0].cache_headers)

    def test_hacs_metadata_and_local_brand_asset(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertEqual(hacs["name"], manifest["name"])
        self.assertFalse(hacs.get("content_in_root", False))
        self.assertTrue(hacs["render_readme"])
        for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners"):
            self.assertTrue(manifest[key], key)
        for filename, size in (("icon.png", 256), ("icon@2x.png", 512)):
            data = (INTEGRATION / "brand" / filename).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack("!II", data[16:24]), (size, size))
