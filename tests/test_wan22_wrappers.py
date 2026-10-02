import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys_path = str(REPO_ROOT / "tools")
import sys

sys.path.insert(0, sys_path)
from audit_wan22_required_files import audit_directory, load_required_files  # noqa: E402
from wan22_modelscope_snapshot import load_snapshot, manifest_rows, manifest_rows_from_tsv, validate_snapshot  # noqa: E402


BASH = shutil.which("bash") or (
    r"D:\Program Files\Git\bin\bash.exe"
    if Path(r"D:\Program Files\Git\bin\bash.exe").is_file()
    else None
)
ENV_WRAPPER = REPO_ROOT / "scripts" / "setup_wan22_env_pack.sh"
WEIGHT_WRAPPER = REPO_ROOT / "scripts" / "download_wan22_t2v_a14b.sh"
MODELSCOPE_MANIFEST = REPO_ROOT / "tools" / "wan22_t2v_a14b_modelscope_required_files.tsv"
MODELSCOPE_SNAPSHOT = REPO_ROOT / "tools" / "wan22_modelscope_api_snapshot.json"


def write_exec(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def run_wrapper(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    merged = os.environ.copy()
    merged.setdefault("WAN22_TEST_MODE", "1")
    merged.update(env)
    return subprocess.run(
        [BASH, str(script)],
        env=merged,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )


@unittest.skipUnless(BASH, "bash is required for wrapper behavior tests")
class Wan22WrapperTest(unittest.TestCase):
    def test_modelscope_manifest_is_exact_metadata_snapshot(self):
        required = load_required_files(MODELSCOPE_MANIFEST)
        self.assertEqual(len(required), 32)
        self.assertEqual(sum(required.values()), 126201624156)
        text = MODELSCOPE_MANIFEST.read_text(encoding="utf-8")
        self.assertIn("# source=modelscope", text)
        self.assertIn("# model_id=Wan-AI/Wan2.2-T2V-A14B", text)
        self.assertIn("# revision=master", text)
        self.assertIn("# blob_count=32", text)
        self.assertIn("# hf_manifest_diff_missing_from_modelscope=.gitattributes", text)
        self.assertIn("# hf_manifest_diff_extra_in_modelscope=.modelscope.diff.ignore", text)
        self.assertEqual(required["high_noise_model/diffusion_pytorch_model-00001-of-00006.safetensors"], 9992481544)
        self.assertEqual(required["low_noise_model/diffusion_pytorch_model-00006-of-00006.safetensors"], 7595559224)

    def test_modelscope_api_snapshot_derives_the_manifest(self):
        payload = load_snapshot(MODELSCOPE_SNAPSHOT)
        rows = validate_snapshot(payload)
        self.assertEqual(len(rows), 32)
        self.assertEqual(sum(int(item["size"]) for item in rows), 126201624156)
        self.assertEqual(manifest_rows(payload), manifest_rows_from_tsv(MODELSCOPE_MANIFEST))
        self.assertEqual(payload["sdk"]["version"], "1.24.1")
        self.assertEqual(payload["query"]["revision"], "master")

    def test_download_source_is_explicit_and_never_cross_falls_back(self):
        text = WEIGHT_WRAPPER.read_text(encoding="utf-8")
        self.assertIn('PROD_REQUIRED_FILES="/public/xbw/Wan2.2/tools/wan22_t2v_a14b_modelscope_required_files.tsv"', text)
        self.assertIn('PROD_MODELSCOPE_BIN="/public/wangwx/softwares/new_Anaconda3/Anaconda3/bin/modelscope"', text)
        self.assertIn('PROD_SNAPSHOT_SHA256="f1291e99b1ba101ddcd550bceb7f4fa84a6a1217cb420f50894e77e7319bc03b"', text)
        self.assertIn('PROD_SNAPSHOT_PY_SHA256="be7300caf97ac6150c1a7fe9e50326b0fe1ede0e6f743763af59d8c64c1014c2"', text)
        self.assertIn('PROD_AUDIT_SHA256="1ce45b58c4de731e53814cd1c7c50b9158e078de067165bf7b1b8cb41e597979"', text)
        self.assertIn('DOWNLOAD_SOURCE="modelscope"', text)
        self.assertIn('REVISION="master"', text)
        self.assertIn('if run_modelscope; then', text)
        self.assertIn('if run_python_modelscope; then', text)
        self.assertIn('if run_huggingface_cli; then', text)
        self.assertNotIn('run_modelscope || run_huggingface_cli', text)
        self.assertIn('MODELSCOPE_BIN="${PROD_MODELSCOPE_BIN}"', text)
        self.assertIn('MODELSCOPE_SELECTED_BIN="${bin}"', text)
        self.assertIn('printf \'modelscope_bin=%s\\n\'', text)
        self.assertIn('realpath -m --', text)
        self.assertIn('mv -T --no-clobber', text)

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_test_mode_rejects_dotdot_symlink_parent_before_mkdir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "public-parent"
            parent.symlink_to(Path("/9950backfile"), target_is_directory=True)
            injected_root = parent / "liujing" / ".." / "liujing" / "zkliu" / "interleaved" / "wan22_t2v_a14b_weights"
            env = {
                "WAN22_RUN_ID": "canonical-injection",
                "WAN22_WEIGHTS_ROOT": str(injected_root),
                "WAN22_WEIGHTS_TARGET": str(root / "model"),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(root / "source"),
                "WAN22_REQUIRED_FILES": str(root / "required.tsv"),
                "WAN22_AUDIT_PY": str(root / "audit.py"),
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("test path would touch production root", result.stderr)
            self.assertFalse((root / "model").exists())

    def test_test_mode_rejects_all_production_auxiliary_paths_before_mkdir(self):
        production = {
            "WAN22_SOURCE_ENV": "/public/wangwx/softwares/new_Anaconda3/Anaconda3/envs/wan22",
            "WAN22_MODELSCOPE_BIN": "/public/wangwx/softwares/new_Anaconda3/Anaconda3/bin/modelscope",
            "WAN22_REQUIRED_FILES": "/public/xbw/Wan2.2/tools/wan22_t2v_a14b_modelscope_required_files.tsv",
            "WAN22_AUDIT_PY": "/public/xbw/Wan2.2/tools/audit_wan22_required_files.py",
            "WAN22_SNAPSHOT": "/public/xbw/Wan2.2/tools/wan22_modelscope_api_snapshot.json",
            "WAN22_SNAPSHOT_PY": "/public/xbw/Wan2.2/tools/wan22_modelscope_snapshot.py",
        }
        for variable, value in production.items():
            with self.subTest(variable=variable), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = {
                    "WAN22_RUN_ID": f"aux-{variable.lower()}",
                    "WAN22_WEIGHTS_ROOT": str(root / "weights"),
                    "WAN22_WEIGHTS_TARGET": str(root / "weights" / "model"),
                    "WAN22_PUBLIC_LINK": str(root / "link"),
                    "WAN22_CONTAINER_TARGET": str(root / "container-model"),
                    "WAN22_SOURCE_ENV": str(root / "source"),
                    "WAN22_REQUIRED_FILES": str(root / "required.tsv"),
                    "WAN22_AUDIT_PY": str(root / "audit.py"),
                    variable: value,
                }
                result = run_wrapper(WEIGHT_WRAPPER, env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("test path would touch production", result.stderr)
                self.assertFalse((root / "weights").exists())

    def test_production_modelscope_bin_cannot_be_changed_by_path_or_override(self):
        text = WEIGHT_WRAPPER.read_text(encoding="utf-8")
        self.assertIn('PROD_MODELSCOPE_BIN="/public/wangwx/softwares/new_Anaconda3/Anaconda3/bin/modelscope"', text)
        self.assertIn('MODELSCOPE_BIN="${PROD_MODELSCOPE_BIN}"', text)
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "WAN22_TEST_MODE": "0",
                "WAN22_RUN_ID": "production-modelscope-override",
                "WAN22_MODELSCOPE_BIN": str(Path(directory) / "fake-modelscope"),
                "PATH": str(Path(directory)) + os.pathsep + os.environ.get("PATH", ""),
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WAN22_MODELSCOPE_BIN", result.stderr)

    def test_test_modelscope_requires_explicit_bin_even_when_path_is_populated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {
                "WAN22_RUN_ID": "missing-modelscope-bin",
                "WAN22_WEIGHTS_ROOT": str(root / "weights"),
                "WAN22_WEIGHTS_TARGET": str(root / "weights" / "model"),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": str(root / "container-model"),
                "WAN22_SOURCE_ENV": str(root / "source"),
                "WAN22_REQUIRED_FILES": str(root / "required.tsv"),
                "WAN22_AUDIT_PY": str(root / "audit.py"),
                "PATH": "/public/wangwx/softwares/new_Anaconda3/Anaconda3/bin:" + os.environ.get("PATH", ""),
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires explicit WAN22_MODELSCOPE_BIN", result.stderr)
            self.assertFalse((root / "weights").exists())

    def test_marker_source_and_manifest_binding_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("file.bin\t4\n", encoding="utf-8")
            audit = root / "audit.py"
            audit.write_text("# fake\n", encoding="utf-8")
            source = root / "source" / "bin"
            source.mkdir(parents=True)
            write_exec(source / "python", "#!/bin/sh\nexit 1\n")
            target = root / "model"
            target.mkdir()
            required_hash = __import__("hashlib").sha256(required.read_bytes()).hexdigest()
            (target / ".wan22_t2v_a14b.identity").write_text(
                "source=hf\nmodel_id=Wan-AI/Wan2.2-T2V-A14B\nrevision=main\n"
                f"manifest_sha256={required_hash}\nrequired_files_sha256={required_hash}\n"
                "expected_file_count=1\nexpected_total_bytes=4\n",
                encoding="utf-8",
            )
            env = {
                "WAN22_RUN_ID": "source-mismatch",
                "WAN22_WEIGHTS_ROOT": str(root),
                "WAN22_WEIGHTS_TARGET": str(target),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(root / "source"),
                "WAN22_REQUIRED_FILES": str(required),
                "WAN22_AUDIT_PY": str(audit),
                "WAN22_DOWNLOAD_SOURCE": "hf",
                "WAN22_MODEL_REVISION": "main",
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing target marker mismatch", (root / "logs" / "source-mismatch.log").read_text())

    def test_required_inventory_missing_and_wrong_size_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("# test\na.bin\t4\nb.bin\t2\n", encoding="utf-8")
            (root / "a.bin").write_bytes(b"bad")
            with self.assertRaises(ValueError):
                audit_directory(root, required)

    def test_required_inventory_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model"
            root.mkdir()
            required = Path(directory) / "required.tsv"
            required.write_text("a.bin\t4\nb.bin\t2\n", encoding="utf-8")
            (root / "a.bin").write_bytes(b"1234")
            (root / "b.bin").write_bytes(b"12")
            result = audit_directory(root, required)
            self.assertTrue(result["complete"])
            self.assertEqual(result["expected_file_count"], 2)
            self.assertEqual(result["expected_total_bytes"], 6)

    def test_required_inventory_rejects_extra_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("a.bin\t4\n", encoding="utf-8")
            (root / "a.bin").write_bytes(b"1234")
            (root / "unexpected.bin").write_bytes(b"x")
            with self.assertRaises(ValueError) as raised:
                audit_directory(root, required)
            self.assertIn("unexpected.bin", str(raised.exception))

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_required_inventory_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("a.bin\t4\n", encoding="utf-8")
            (root / "real.bin").write_bytes(b"1234")
            (root / "a.bin").symlink_to(root / "real.bin")
            with self.assertRaises(ValueError) as raised:
                audit_directory(root, required)
            self.assertIn("a.bin", str(raised.exception))

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_required_inventory_rejects_symlink_root(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            real_root = parent / "real-model"
            real_root.mkdir()
            required = parent / "required.tsv"
            required.write_text("a.bin\t4\n", encoding="utf-8")
            (real_root / "a.bin").write_bytes(b"1234")
            link_root = parent / "model-link"
            link_root.symlink_to(real_root, target_is_directory=True)
            with self.assertRaises(ValueError):
                audit_directory(link_root, required)

    def test_production_rejects_path_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {
                "WAN22_TEST_MODE": "0",
                "WAN22_RUN_ID": "production-injection",
                "WAN22_WEIGHTS_ROOT": str(root),
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("production path/source override is forbidden", result.stderr)

    def test_weight_lock_failure_writes_unique_exit_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("file.bin\t4\n", encoding="utf-8")
            audit = root / "audit.py"
            audit.write_text("# fake\n", encoding="utf-8")
            source = root / "source" / "bin"
            source.mkdir(parents=True)
            write_exec(source / "python", "#!/bin/sh\nexit 1\n")
            (root / ".download.lock").mkdir()
            env = {
                "WAN22_RUN_ID": "lock-test",
                "WAN22_WEIGHTS_ROOT": str(root),
                "WAN22_WEIGHTS_TARGET": str(root / "model"),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(root / "source"),
                "WAN22_REQUIRED_FILES": str(required),
                "WAN22_AUDIT_PY": str(audit),
                "WAN22_DOWNLOAD_SOURCE": "hf",
                "WAN22_MODEL_REVISION": "main",
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertEqual(result.returncode, 3, result.stderr)
            marker = root / "logs" / "lock-test.exit"
            self.assertTrue(marker.is_file())
            self.assertIn("exit_code=3", marker.read_text(encoding="utf-8"))

    def test_weight_unknown_target_rejected_with_exit_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("file.bin\t4\n", encoding="utf-8")
            audit = root / "audit.py"
            audit.write_text("# fake\n", encoding="utf-8")
            source = root / "source" / "bin"
            source.mkdir(parents=True)
            write_exec(source / "python", "#!/bin/sh\nexit 1\n")
            target = root / "model"
            target.mkdir()
            env = {
                "WAN22_RUN_ID": "unknown-target",
                "WAN22_WEIGHTS_ROOT": str(root),
                "WAN22_WEIGHTS_TARGET": str(target),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(root / "source"),
                "WAN22_REQUIRED_FILES": str(required),
                "WAN22_AUDIT_PY": str(audit),
                "WAN22_DOWNLOAD_SOURCE": "hf",
                "WAN22_MODEL_REVISION": "main",
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing target marker mismatch", (root / "logs" / "unknown-target.log").read_text())
            self.assertIn("exit_code=2", (root / "logs" / "unknown-target.exit").read_text())

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_weight_failure_marker_and_complete_link_publish_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("file.bin\t4\n", encoding="utf-8")
            audit = root / "audit.py"
            audit.write_text("# fake\n", encoding="utf-8")
            source = root / "source" / "bin"
            source.mkdir(parents=True)
            write_exec(
                source / "python",
                "#!/bin/sh\nif [ \"$1\" = \"-c\" ]; then exit 1; fi\n"
                "out=; while [ $# -gt 0 ]; do if [ \"$1\" = \"--output\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "[ -z \"$out\" ] || printf '{\\\"complete\\\": true}\\n' > \"$out\"\n",
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            write_exec(
                bin_dir / "modelscope",
                "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo test-modelscope; exit 0; fi\n"
                "out=; while [ $# -gt 0 ]; do if [ \"$1\" = \"--local_dir\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "mkdir -p \"$out\"; printf 1234 > \"$out/file.bin\"\n",
            )
            # The remote Lance/Wan environments may provide a real
            # huggingface-cli.  Keep this failure-path test offline and
            # deterministic: all downloader fallbacks must fail locally.
            write_exec(bin_dir / "huggingface-cli", "#!/bin/sh\nexit 7\n")
            env_base = {
                "WAN22_WEIGHTS_ROOT": str(root),
                "WAN22_WEIGHTS_TARGET": str(root / "model"),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(root / "source"),
                "WAN22_REQUIRED_FILES": str(required),
                "WAN22_AUDIT_PY": str(audit),
                "WAN22_MODELSCOPE_BIN": str(bin_dir / "modelscope"),
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
            }
            failed_env = {**env_base, "WAN22_RUN_ID": "download-fail"}
            write_exec(bin_dir / "modelscope", "#!/bin/sh\nexit 7\n")
            write_exec(
                bin_dir / "huggingface-cli",
                "#!/bin/sh\ntouch \"$WAN22_WEIGHTS_ROOT/hf-called\"\nexit 0\n",
            )
            failed = run_wrapper(WEIGHT_WRAPPER, failed_env)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse((root / "link").exists())
            self.assertFalse((root / "hf-called").exists())
            self.assertIn("exit_code=", (root / "logs" / "download-fail.exit").read_text())
            self.assertFalse((root / ".download.lock").exists())

            write_exec(
                bin_dir / "modelscope",
                "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then exit 0; fi\n"
                "out=; while [ $# -gt 0 ]; do if [ \"$1\" = \"--local_dir\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "mkdir -p \"$out\"; printf 1234 > \"$out/file.bin\"\n",
            )
            success_env = {**env_base, "WAN22_RUN_ID": "download-ok"}
            success = run_wrapper(WEIGHT_WRAPPER, success_env)
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertTrue((root / "link").is_symlink())
            self.assertTrue((root / "model" / ".wan22_t2v_a14b.complete").is_file())
            self.assertFalse((root / ".download.lock").exists())

            resume_env = {**env_base, "WAN22_RUN_ID": "download-resume"}
            resumed = run_wrapper(WEIGHT_WRAPPER, resume_env)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertFalse((root / ".download.lock").exists())

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_weight_publish_ln_failure_is_nonzero_without_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = Path(directory) / "required.tsv"
            required.write_text("file.bin\t4\n", encoding="utf-8")
            audit = root / "audit.py"
            audit.write_text("# fake\n", encoding="utf-8")
            source = root / "source" / "bin"
            source.mkdir(parents=True)
            write_exec(
                source / "python",
                "#!/bin/sh\nif [ \"$1\" = \"-c\" ]; then exit 1; fi\n"
                "out=; while [ $# -gt 0 ]; do if [ \"$1\" = \"--output\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "[ -z \"$out\" ] || printf '{\\\"complete\\\": true}\\n' > \"$out\"\n",
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            write_exec(
                bin_dir / "modelscope",
                "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then exit 0; fi\n"
                "out=; while [ $# -gt 0 ]; do if [ \"$1\" = \"--local_dir\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "mkdir -p \"$out\"; printf 1234 > \"$out/file.bin\"\n",
            )
            write_exec(bin_dir / "ln", "#!/bin/sh\nexit 17\n")
            env = {
                "WAN22_RUN_ID": "publish-ln-fail",
                "WAN22_WEIGHTS_ROOT": str(root),
                "WAN22_WEIGHTS_TARGET": str(root / "model"),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(root / "source"),
                "WAN22_REQUIRED_FILES": str(required),
                "WAN22_AUDIT_PY": str(audit),
                "WAN22_MODELSCOPE_BIN": str(bin_dir / "modelscope"),
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "link").exists())
            self.assertIn("exit_code=", (root / "logs" / "publish-ln-fail.exit").read_text())

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_existing_complete_symlink_is_not_written_or_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = root / "required.tsv"
            required.write_text("file.bin\t4\n", encoding="utf-8")
            audit = root / "audit.py"
            audit.write_text("# fake\n", encoding="utf-8")
            source = root / "source" / "bin"
            source.mkdir(parents=True)
            write_exec(
                source / "python",
                "#!/bin/sh\nif [ \"$1\" = \"-c\" ]; then exit 1; fi\n"
                "out=; while [ $# -gt 0 ]; do if [ \"$1\" = \"--output\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "[ -z \"$out\" ] || printf '{\\\"complete\\\": true}\\n' > \"$out\"\n",
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            external = root / "external-marker"
            external.write_text("do-not-touch\n", encoding="utf-8")
            write_exec(
                bin_dir / "modelscope",
                "#!/bin/sh\n"
                "out=; for arg in \"$@\"; do case \"$arg\" in /*) out=\"$arg\";; esac; done\n"
                "mkdir -p \"$out\"; printf 1234 > \"$out/file.bin\"; "
                "ln -s \"$EXTERNAL_MARKER\" \"$out/.wan22_t2v_a14b.complete\"\n",
            )
            env = {
                "WAN22_RUN_ID": "complete-symlink",
                "WAN22_WEIGHTS_ROOT": str(root),
                "WAN22_WEIGHTS_TARGET": str(root / "model"),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(source.parent),
                "WAN22_REQUIRED_FILES": str(required),
                "WAN22_AUDIT_PY": str(audit),
                "WAN22_MODELSCOPE_BIN": str(bin_dir / "modelscope"),
                "EXTERNAL_MARKER": str(external),
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((root / "model" / ".wan22_t2v_a14b.complete").is_symlink())
            self.assertEqual(external.read_text(encoding="utf-8"), "do-not-touch\n")
            self.assertIn("existing complete marker is missing or mismatched", (root / "logs" / "complete-symlink.log").read_text())

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_target_directory_replacement_is_rejected_without_touching_external(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = root / "required.tsv"
            required.write_text("file.bin\t4\n", encoding="utf-8")
            audit = root / "audit.py"
            audit.write_text("# fake\n", encoding="utf-8")
            source = root / "source" / "bin"
            source.mkdir(parents=True)
            write_exec(source / "python", "#!/bin/sh\nif [ \"$1\" = \"-c\" ]; then exit 1; fi\nexit 0\n")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            external = root / "external-model"
            external.mkdir()
            sentinel = external / "sentinel"
            sentinel.write_text("do-not-touch\n", encoding="utf-8")
            write_exec(
                bin_dir / "modelscope",
                "#!/bin/sh\n"
                "out=; while [ $# -gt 0 ]; do if [ \"$1\" = \"--local_dir\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "rm -rf \"$out\"; ln -s \"$EXTERNAL_MODEL\" \"$out\"\n",
            )
            env = {
                "WAN22_RUN_ID": "target-race",
                "WAN22_WEIGHTS_ROOT": str(root),
                "WAN22_WEIGHTS_TARGET": str(root / "model"),
                "WAN22_PUBLIC_LINK": str(root / "link"),
                "WAN22_CONTAINER_TARGET": "/container/model",
                "WAN22_SOURCE_ENV": str(source.parent),
                "WAN22_REQUIRED_FILES": str(required),
                "WAN22_AUDIT_PY": str(audit),
                "WAN22_MODELSCOPE_BIN": str(bin_dir / "modelscope"),
                "EXTERNAL_MODEL": str(external),
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
            }
            result = run_wrapper(WEIGHT_WRAPPER, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((root / "model").is_symlink())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do-not-touch\n")
            self.assertFalse((root / "link").exists())
            self.assertIn("target directory was replaced or symlinked", (root / "logs" / "target-race.log").read_text())

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_environment_pack_lock_and_versioned_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup = root / "setup"
            source = root / "source"
            source.mkdir()
            fake_pack = root / "conda-pack"
            write_exec(
                fake_pack,
                "#!/bin/sh\nout=; while [ $# -gt 0 ]; do if [ \"$1\" = \"-o\" ]; then out=$2; shift 2; else shift; fi; done\n"
                "tmp=$(mktemp -d); mkdir -p \"$tmp/bin\"; printf '#!/bin/sh\\nexit 0\\n' > \"$tmp/bin/conda-unpack\"; printf '#!/bin/sh\\nif [ \"$1\" = \"-c\" ]; then printf \'0.8.1\\n\'; fi\\nexit 0\\n' > \"$tmp/bin/python\"; chmod +x \"$tmp/bin/conda-unpack\" \"$tmp/bin/python\"; tar -czf \"$out\" -C \"$tmp\" .; rm -rf \"$tmp\"\n",
            )
            lock = setup / ".env-pack.lock"
            lock.mkdir(parents=True)
            env = {
                "WAN22_RUN_ID": "env-lock",
                "WAN22_SETUP_ROOT": str(setup),
                "WAN22_SOURCE_ENV": str(source),
                "WAN22_CONDA_PACK": str(fake_pack),
                "WAN22_FIXED_ENV": str(root / "fixed"),
                "WAN22_VERSIONED_ENV": str(root / "versioned-lock"),
                "WAN22_TEMP_ENV": str(root / "temporary-lock"),
            }
            locked = run_wrapper(ENV_WRAPPER, env)
            self.assertEqual(locked.returncode, 3, locked.stderr)
            self.assertIn("exit_code=3", (setup / "logs" / "env-lock.exit").read_text())
            lock.rmdir()

            env["WAN22_RUN_ID"] = "env-ok"
            env["WAN22_VERSIONED_ENV"] = str(root / "versioned-ok")
            env["WAN22_TEMP_ENV"] = str(root / "temporary-ok")
            completed = run_wrapper(ENV_WRAPPER, env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((root / "fixed").is_symlink())
            self.assertEqual((root / "fixed").resolve(), (root / "versioned-ok").resolve())
            self.assertFalse((setup / ".env-pack.lock").exists())
            self.assertIn("einops_version=0.8.1", (setup / "logs" / "env-ok.identity").read_text(encoding="utf-8"))
            self.assertIn("decord_version=0.8.1", (setup / "logs" / "env-ok.identity").read_text(encoding="utf-8"))

    def test_initialization_failure_writes_bootstrap_marker(self):
        for failure_kind in ("logdir", "identity"):
            with self.subTest(failure_kind=failure_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                setup = root / "setup"
                setup.mkdir()
                run_id = f"init-{failure_kind}"
                if failure_kind == "logdir":
                    (setup / "logs").write_text("not-a-directory", encoding="utf-8")
                else:
                    (setup / "logs").mkdir()
                    (setup / "logs" / f"{run_id}.identity").mkdir()
                env = {
                    "WAN22_RUN_ID": run_id,
                    "WAN22_SETUP_ROOT": str(setup),
                    "WAN22_SOURCE_ENV": str(root / "source"),
                    "WAN22_CONDA_PACK": str(root / "conda-pack"),
                    "WAN22_FIXED_ENV": str(root / "fixed"),
                    "WAN22_VERSIONED_ENV": str(root / "versioned"),
                    "WAN22_TEMP_ENV": str(root / "temporary"),
                }
                result = run_wrapper(ENV_WRAPPER, env)
                self.assertNotEqual(result.returncode, 0)
                boot_exit = setup / ".run-markers" / f"{run_id}.exit"
                self.assertTrue(boot_exit.is_file())
                self.assertIn("exit_code=", boot_exit.read_text(encoding="utf-8"))


class Wan22WrapperStaticTest(unittest.TestCase):
    def test_safety_contract_is_present(self):
        for script in (ENV_WRAPPER, WEIGHT_WRAPPER):
            text = script.read_text(encoding="utf-8")
            self.assertIn("set -Eeuo pipefail", text)
            self.assertIn("trap on_exit EXIT", text)
            self.assertIn("RUN_ID=", text)
            self.assertIn(".lock", text)
            self.assertIn("exit_code=", text)

    def test_environment_publish_requires_einops_import_and_records_version(self):
        text = ENV_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("import einops, importlib.metadata", text)
        self.assertIn("einops_version=", text)
        self.assertIn("import decord, importlib.metadata", text)
        self.assertIn("decord_version=", text)
        self.assertIn('mv -- "${TEMP_ENV}" "${VERSIONED_ENV}"', text)


if __name__ == "__main__":
    unittest.main()
