import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
SMOKE_RUNNER = REPO_ROOT / "scripts" / "run_t2v_smoke.sh"
BASH = shutil.which("bash") or (
    r"D:\Program Files\Git\bin\bash.exe"
    if Path(r"D:\Program Files\Git\bin\bash.exe").is_file()
    else None
)

import validate_wan_smoke_output as validator  # noqa: E402
from validate_wan_smoke_output import validate_video  # noqa: E402
import write_wan_smoke_manifest as manifest_writer  # noqa: E402
from write_wan_smoke_manifest import read_prompts  # noqa: E402


VALID_METADATA = {
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "5.0625", "size": "12"},
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 832,
            "height": 480,
            "avg_frame_rate": "16/1",
            "nb_read_frames": "81",
        }
    ],
}


class WanSmokeToolTest(unittest.TestCase):
    def test_smoke_runner_has_fixed_production_model_and_test_isolation(self):
        text = SMOKE_RUNNER.read_text(encoding="utf-8")
        self.assertIn('PROD_MODEL_LINK="/public/xbw/Wan2.2-T2V-A14B"', text)
        self.assertIn('PROD_REPO_DIR="/public/xbw/Wan2.2"', text)
        self.assertIn('PROD_RUN_ROOT_BASE="/storage-root/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_smoke"', text)
        self.assertIn('PROD_MODEL_SOURCE="modelscope"', text)
        self.assertIn('PROD_MODEL_REVISION="master"', text)
        self.assertIn('PROD_MANIFEST_SHA256="3cfb749560e87a7b1cc2faa14cbb59860d66600447014436ddb1625dba1dbe1f"', text)
        self.assertIn('WAN_TEST_MODE="${WAN_TEST_MODE:-0}"', text)
        self.assertIn("production model path override is forbidden", text)
        self.assertIn("test model path may not touch the production Wan2.2 link", text)
        self.assertIn('PROD_CONTAINER_TARGET="/storage-root/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_weights/Wan2.2-T2V-A14B"', text)
        self.assertIn('PROD_PYTHON_BIN="/public/wangwx/softwares/new_Anaconda3/Anaconda3/envs/wan22/bin/python"', text)
        self.assertIn('PROD_TORCHRUN_BIN="/public/wangwx/softwares/new_Anaconda3/Anaconda3/envs/wan22/bin/torchrun"', text)
        self.assertIn('PROD_NUM_GPUS=8', text)
        self.assertIn('PROD_SIZE="832*480"', text)
        self.assertIn('PROD_SAMPLE_STEPS=40', text)
        self.assertIn('PROD_FRAME_NUM=81', text)
        self.assertIn('PROD_EXPECTED_FPS=16', text)
        self.assertIn('PROD_ALLOWED_CODECS="h264"', text)
        self.assertIn('PROD_MAX_PROMPTS=2', text)
        self.assertIn('PROD_PROMPT_FILE_RELATIVE="prompts/t2v_smoke_prompts.tsv"', text)
        self.assertIn('PROD_PROMPTS_SHA256="7defd5827ccb7868b45ca4a23cc4e3c4525f8aa8d88a171205a93780a40e30d1"', text)
        self.assertIn('PROD_SELECTED_PROMPTS_SHA256="9c3d212d44888bce1d6b206142e63bf5dbc91ca9dcef9e82abc25b0bf724c0f3"', text)
        for override in (
            "WAN_PYTHON_BIN",
            "WAN_TORCHRUN_BIN",
            "WAN_PROMPTS_FILE",
            "WAN_NUM_GPUS",
            "WAN_SIZE",
            "WAN_SAMPLE_STEPS",
            "WAN_FRAME_NUM",
            "WAN_EXPECTED_FPS",
            "WAN_ALLOWED_CODECS",
            "WAN_MAX_PROMPTS",
        ):
            self.assertIn(override, text)
        self.assertIn("verify_fixed_model_contract", text)
        self.assertIn("import decord", text)
        self.assertIn("selected_prompt_ids", (REPO_ROOT / "tools" / "write_wan_smoke_manifest.py").read_text(encoding="utf-8"))

    @unittest.skipUnless(BASH and os.name != "nt", "POSIX symlink canonicalization is required")
    def test_smoke_test_mode_rejects_dotdot_symlink_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "public-parent"
            parent.symlink_to(Path("/public/xbw"), target_is_directory=True)
            injected = parent / "Wan2.2-T2V-A14B" / ".." / "Wan2.2-T2V-A14B"
            env = os.environ.copy()
            env.update(
                {
                    "WAN_TEST_MODE": "1",
                    "WAN_REPO_DIR": str(REPO_ROOT),
                    "WAN_RUN_ROOT": str(root / "run"),
                    "WAN_MODEL_DIR": str(injected),
                    "WAN_PROMPTS_FILE": str(REPO_ROOT / "prompts" / "t2v_smoke_prompts.tsv"),
                }
            )
            result = subprocess.run(
                [BASH, str(SMOKE_RUNNER)],
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("test path would touch production model_dir", result.stderr)

    @unittest.skipUnless(BASH and os.name != "nt", "requires POSIX shell execution")
    def test_production_repo_and_run_root_contract_is_strict(self):
        base_env = os.environ.copy()
        base_env.update(
            {
                "WAN_TEST_MODE": "0",
                "WAN_REPO_DIR": "/tmp/not-the-canonical-wan-repo",
                "WAN_RUN_ROOT": "/storage-root/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_smoke/run",
            }
        )
        result = subprocess.run([BASH, str(SMOKE_RUNNER)], env=base_env, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("production WAN_REPO_DIR must equal", result.stderr)

        base_env["WAN_REPO_DIR"] = "/public/xbw/Wan2.2"
        base_env["WAN_RUN_ROOT"] = "/storage-root/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_smoke"
        result = subprocess.run([BASH, str(SMOKE_RUNNER)], env=base_env, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("production WAN_RUN_ROOT must be a unique child", result.stderr)

    def test_manifest_records_only_selected_prompts_and_fixed_production_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / "run"
            (run_root / "videos").mkdir(parents=True)
            (run_root / "metadata").mkdir()
            prompts = root / "prompts.tsv"
            prompts.write_text("a\t1\tone\nb\t2\ttwo\nc\t3\tthree\n", encoding="utf-8")
            output = run_root / "manifest.json"
            argv = [
                "write_wan_smoke_manifest.py",
                "--output", str(output), "--repo", str(REPO_ROOT),
                "--model-dir", str(root / "model"), "--prompts", str(prompts),
                "--run-id", "selected", "--run-root", str(run_root),
                "--status", "failed", "--exit-code", "1", "--test-mode", "0",
                "--selected-prompt-id", "a", "--selected-prompt-id", "b",
                "--max-prompts", "2",
            ]
            with patch.object(manifest_writer, "source_identity", return_value={}), patch.object(
                manifest_writer, "environment_report", return_value={}
            ), patch.object(manifest_writer, "model_inventory", return_value={}):
                with patch.object(sys, "argv", argv):
                    manifest_writer.main()
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["model"]["source"], "modelscope")
            self.assertEqual(payload["model"]["revision"], "master")
            self.assertEqual(payload["inputs"]["selected_prompt_ids"], ["a", "b"])
            self.assertEqual(payload["inputs"]["max_prompts"], 2)
            self.assertEqual([item["id"] for item in payload["inputs"]["prompts"]], ["a", "b"])

    def test_requirements_explicitly_include_einops(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(requirements, r"(?m)^einops(?:[<>=!].*)?$")

    def test_requirements_pin_decord(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(requirements, r"(?m)^decord==0\.6\.0$")

    def test_environment_report_records_einops_version(self):
        with patch.object(
            manifest_writer.importlib.metadata,
            "version",
            side_effect=lambda name: f"test-{name}",
        ):
            report = manifest_writer.environment_report()
        self.assertEqual(report["packages"]["einops"], "test-einops")
        self.assertEqual(report["packages"]["decord"], "test-decord")

    def test_prompt_invalid_id_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.tsv"
            path.write_text("bad/id\t1\tprompt\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_prompts(path)

    def test_prompt_duplicate_id_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.tsv"
            path.write_text("same\t1\tone\nsame\t2\ttwo\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_prompts(path)

    def test_valid_mp4_metadata_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            metadata = root / "sample.json"
            video.write_bytes(b"not-a-real-mp4-but-nonempty")
            metadata.write_text(json.dumps(VALID_METADATA), encoding="utf-8")
            result = validate_video(video, metadata, "832*480", 81)
            self.assertEqual(result["metadata_path"], str(metadata))
            self.assertIsInstance(result["ffprobe"], dict)
            self.assertEqual(result["ffprobe"]["video"]["width"], 832)
            self.assertEqual(result["ffprobe"]["video"]["frame_count"], 81)

    def test_write_normalized_is_object_and_revalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            metadata = root / "sample.json"
            video.write_bytes(b"fake")
            metadata.write_text(json.dumps(VALID_METADATA), encoding="utf-8")
            argv = [
                "validate_wan_smoke_output.py",
                "--video",
                str(video),
                "--metadata",
                str(metadata),
                "--size",
                "832*480",
                "--frame-num",
                "81",
                "--write-normalized",
            ]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                validator.main()
            written = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertIsInstance(written, dict)
            self.assertIn("video", written)
            second = validate_video(video, metadata, "832*480", 81)
            self.assertEqual(second["ffprobe"], written)

    def test_fake_mp4_wrong_container_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            metadata = root / "sample.json"
            video.write_bytes(b"fake")
            wrong = json.loads(json.dumps(VALID_METADATA))
            wrong["format"]["format_name"] = "matroska,webm"
            metadata.write_text(json.dumps(wrong), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_video(video, metadata, "832*480", 81)

    def test_wrong_fps_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            metadata = root / "sample.json"
            video.write_bytes(b"fake")
            wrong = json.loads(json.dumps(VALID_METADATA))
            wrong["streams"][0]["avg_frame_rate"] = "15/1"
            metadata.write_text(json.dumps(wrong), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_video(video, metadata, "832*480", 81)

    def test_empty_or_unsupported_codec_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            metadata = root / "sample.json"
            video.write_bytes(b"fake")
            for codec in ("", "vp9"):
                wrong = json.loads(json.dumps(VALID_METADATA))
                wrong["streams"][0]["codec_name"] = codec
                metadata.write_text(json.dumps(wrong), encoding="utf-8")
                with self.assertRaises(ValueError):
                    validate_video(video, metadata, "832*480", 81)

    def test_failed_metadata_still_writes_failed_manifest(self):
        for bad_metadata in ("", "{"):
            with self.subTest(metadata=bad_metadata), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                run_root = root / "run"
                (run_root / "videos").mkdir(parents=True)
                (run_root / "metadata").mkdir()
                video = run_root / "videos" / "sample.mp4"
                metadata = run_root / "metadata" / "sample.json"
                video.write_bytes(b"fake")
                metadata.write_text(bad_metadata, encoding="utf-8")
                prompts = root / "prompts.tsv"
                prompts.write_text("sample\t1\tprompt\n", encoding="utf-8")
                manifest_path = run_root / "manifest.json"
                argv = [
                    "write_wan_smoke_manifest.py",
                    "--output",
                    str(manifest_path),
                    "--repo",
                    str(REPO_ROOT),
                    "--model-dir",
                    str(root / "model"),
                    "--prompts",
                    str(prompts),
                    "--run-id",
                    "failed-metadata",
                    "--run-root",
                    str(run_root),
                    "--status",
                    "failed",
                    "--exit-code",
                    "1",
                    "--output-file",
                    str(video),
                ]
                with patch.object(manifest_writer, "source_identity", return_value={}), patch.object(
                    manifest_writer, "environment_report", return_value={}
                ), patch.object(manifest_writer, "model_inventory", return_value={}):
                    with patch.object(sys, "argv", argv):
                        manifest_writer.main()
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                output = manifest["outputs"][0]
                self.assertEqual(manifest["status"], "failed")
                self.assertEqual(manifest["exit_code"], 1)
                self.assertIsNone(output["ffprobe"])
                self.assertIn("metadata_error", output)

    def test_wrong_resolution_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            metadata = root / "sample.json"
            video.write_bytes(b"fake")
            wrong = json.loads(json.dumps(VALID_METADATA))
            wrong["streams"][0]["width"] = 480
            wrong["streams"][0]["height"] = 832
            metadata.write_text(json.dumps(wrong), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_video(video, metadata, "832*480", 81)


if __name__ == "__main__":
    unittest.main()
