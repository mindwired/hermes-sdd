from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class MockContext:
    def __init__(self) -> None:
        self.tools = []
        self.commands = []
        self.cli = []
        self.skills = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_command(self, name, handler, **kwargs):
        self.commands.append((name, handler, kwargs))

    def register_cli_command(self, name, **kwargs):
        self.cli.append((name, kwargs))

    def register_skill(self, name, path):
        self.skills.append((name, Path(path)))


def load_like_hermes():
    parent = "hermes_plugins_test"
    package = f"{parent}.sdd"
    ns = types.ModuleType(parent)
    ns.__path__ = []
    sys.modules[parent] = ns
    spec = importlib.util.spec_from_file_location(
        package,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    module.__package__ = package
    module.__path__ = [str(ROOT)]
    sys.modules[package] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        for name in [
            item for item in sys.modules if item == parent or item.startswith(parent + ".")
        ]:
            sys.modules.pop(name, None)


class RegistrationTest(unittest.TestCase):
    def test_registers_compact_cross_surface_contract(self) -> None:
        root_plugin = load_like_hermes()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"HERMES_HOME": temp}):
            context = MockContext()
            root_plugin.register(context)
            self.assertFalse((Path(temp) / "sdd" / "sources.db").exists())
        self.assertEqual([item["name"] for item in context.tools], ["sdd"])
        description = context.tools[0]["schema"]["description"]
        self.assertIn("sdd:sdd-start", description)
        self.assertIn("sdd:sdd-plan", description)
        self.assertIn("sdd:sdd-execute", description)
        self.assertIn("sdd:sdd-verify", description)
        self.assertNotIn("plugin:sdd-", description)
        self.assertEqual(
            {item[0] for item in context.commands},
            {"sdd", "sdd-status", "sdd-next", "sdd-validate"},
        )
        self.assertEqual([item[0] for item in context.cli], ["sdd"])
        self.assertEqual(
            {item[0] for item in context.skills},
            {"sdd-start", "sdd-plan", "sdd-execute", "sdd-verify", "sdd-recover"},
        )
        self.assertTrue(all(path.is_file() for _, path in context.skills))


if __name__ == "__main__":
    unittest.main()
