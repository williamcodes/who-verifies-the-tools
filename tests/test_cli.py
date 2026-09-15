import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiment"
DATA = EXPERIMENT.parent / "data"


class TestOfflineCLI(unittest.TestCase):
    def run_python(self, *args, cwd=ROOT):
        env = {
            key: value
            for key, value in os.environ.items()
            if not any(s in key.upper() for s in ("API_KEY", "TOKEN", "PYTHONPATH"))
        }
        return subprocess.run(
            [sys.executable, "-S", "-B", *args],
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_imports_require_neither_site_packages_nor_archive_modules(self):
        code = """
import sys
from experiment import harness, analyze, build_manifest, contract_checker
from experiment import grading as rig
assert not ({"rag", "db_manager", "config", "numpy", "langgraph"} & sys.modules.keys())
assert rig.ITEMS == []
"""
        result = self.run_python("-c", code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_package_and_direct_script_replay(self):
        for command in [
            ("-m", "experiment.build_manifest"),
            ("experiment/build_manifest.py",),
        ]:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                result = self.run_python(*command, "--replay", "--output-dir", tmp)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    (Path(tmp) / "manifest.json").read_bytes(),
                    (DATA / "cases/manifest.json").read_bytes(),
                )

    def test_existing_live_cli_help_is_offline(self):
        for script in ("harness.py", "build_manifest.py", "grading.py"):
            with self.subTest(script=script):
                result = self.run_python(
                    str(EXPERIMENT / script), "--help", cwd=EXPERIMENT
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)

    def test_replay_requires_output_and_never_defaults_to_frozen_directory(self):
        result = self.run_python("-m", "experiment.build_manifest", "--replay")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--replay requires --output-dir", result.stderr)
