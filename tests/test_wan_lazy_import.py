import os
import importlib.util
import subprocess
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WAN_RUNTIME_AVAILABLE = importlib.util.find_spec("torch") is not None


def load_init_with_stubs():
    """Execute the package initializer without importing Wan's torch stack."""

    package_name = "_wan_lazy_import_probe"
    stale_names = [
        name for name in sys.modules if name == package_name or name.startswith(package_name + ".")
    ]
    for name in stale_names:
        sys.modules.pop(name, None)

    package = types.ModuleType(package_name)
    package.__file__ = str(REPO_ROOT / "wan" / "__init__.py")
    package.__path__ = []
    package.__package__ = package_name
    sys.modules[package_name] = package
    for child_name in ("configs", "distributed", "modules"):
        qualified_name = f"{package_name}.{child_name}"
        child = types.ModuleType(qualified_name)
        setattr(package, child_name, child)
        sys.modules[qualified_name] = child

    source = (REPO_ROOT / "wan" / "__init__.py").read_text(encoding="utf-8")
    exec(compile(source, str(REPO_ROOT / "wan" / "__init__.py"), "exec"), package.__dict__)
    return package, package_name


class WanLazyImportTest(unittest.TestCase):
    @unittest.skipUnless(WAN_RUNTIME_AVAILABLE, "Wan runtime dependencies are unavailable")
    def test_import_wan_does_not_load_s2v_when_librosa_is_blocked(self):
        script = r'''
import sys
sys.modules["librosa"] = None
import wan

assert "wan.speech2video" not in sys.modules
assert "wan.modules.s2v" not in sys.modules
assert "WanS2V" not in wan.__dict__
assert "WanS2V" in wan.__all__
assert "WanS2V" in dir(wan)
'''
        env = os.environ.copy()
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) + (
            os.pathsep + existing if existing else ""
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(WAN_RUNTIME_AVAILABLE, "Wan runtime dependencies are unavailable")
    def test_accessing_want2v_loads_only_the_t2v_module(self):
        script = r'''
import sys
import wan

assert "wan.text2video" not in sys.modules
model_entrypoint = wan.WanT2V
assert model_entrypoint.__module__ == "wan.text2video"
assert "wan.text2video" in sys.modules
assert wan.WanT2V is model_entrypoint
'''
        env = os.environ.copy()
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) + (
            os.pathsep + existing if existing else ""
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lazy_mapping_imports_and_caches_each_export(self):
        wan, package_name = load_init_with_stubs()
        for name, (module_name, attribute_name) in wan._LAZY_EXPORTS.items():
            qualified_name = f"{package_name}{module_name}"
            fake_module = types.ModuleType(qualified_name)
            fake_value = object()
            setattr(fake_module, attribute_name, fake_value)
            original_module = sys.modules.get(qualified_name)
            try:
                sys.modules[qualified_name] = fake_module
                wan.__dict__.pop(name, None)
                self.assertIs(getattr(wan, name), fake_value)
                self.assertIs(getattr(wan, name), fake_value)
                self.assertIs(wan.__dict__[name], fake_value)
            finally:
                if original_module is None:
                    sys.modules.pop(qualified_name, None)
                else:
                    sys.modules[qualified_name] = original_module
                wan.__dict__.pop(name, None)

    def test_unknown_attribute_raises_attribute_error(self):
        wan, _ = load_init_with_stubs()

        with self.assertRaises(AttributeError):
            getattr(wan, "NotARealWanEntryPoint")


if __name__ == "__main__":
    unittest.main()
