#!/usr/bin/env bash
set -Eeuo pipefail

# Official Wan2.2 T2V-A14B multi-GPU smoke runner.  It intentionally does not
# enable prompt extension: no DashScope/API credentials are needed for this
# reproducible smoke test.

: "${WAN_REPO_DIR:?set WAN_REPO_DIR to the immutable source checkout}"
: "${WAN_RUN_ROOT:?set WAN_RUN_ROOT to the task output directory}"

# Production always consumes the audited, atomically published model link.
# Temporary model paths are available only with an explicit test-mode switch;
# this keeps a typo in a test from silently changing the production contract.
WAN_TEST_MODE="${WAN_TEST_MODE:-0}"
PROD_MODEL_LINK="/public/xbw/Wan2.2-T2V-A14B"
PROD_REPO_DIR="/public/xbw/Wan2.2"
PROD_RUN_ROOT_BASE="/storage-root/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_smoke"
PROD_CONTAINER_TARGET="/storage-root/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_weights/Wan2.2-T2V-A14B"
PROD_WEIGHT_ROOT="/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_weights"
PROD_WEIGHT_TARGET="${PROD_WEIGHT_ROOT}/Wan2.2-T2V-A14B"
PROD_MODEL_REPO_ID="Wan-AI/Wan2.2-T2V-A14B"
PROD_MODEL_SOURCE="modelscope"
PROD_MODEL_REVISION="master"
PROD_MANIFEST_SHA256="3cfb749560e87a7b1cc2faa14cbb59860d66600447014436ddb1625dba1dbe1f"
PROD_AUDIT_SHA256="1ce45b58c4de731e53814cd1c7c50b9158e078de067165bf7b1b8cb41e597979"
PROD_FILE_COUNT=32
PROD_TOTAL_BYTES=126201624156
PROD_PYTHON_BIN="/public/wangwx/softwares/new_Anaconda3/Anaconda3/envs/wan22/bin/python"
PROD_TORCHRUN_BIN="/public/wangwx/softwares/new_Anaconda3/Anaconda3/envs/wan22/bin/torchrun"
PROD_PROMPT_FILE_RELATIVE="prompts/t2v_smoke_prompts.tsv"
PROD_PROMPTS_SHA256="7defd5827ccb7868b45ca4a23cc4e3c4525f8aa8d88a171205a93780a40e30d1"
PROD_SELECTED_PROMPTS_SHA256="9c3d212d44888bce1d6b206142e63bf5dbc91ca9dcef9e82abc25b0bf724c0f3"
PROD_NUM_GPUS=8
PROD_SIZE="832*480"
PROD_SAMPLE_STEPS=40
PROD_FRAME_NUM=81
PROD_EXPECTED_FPS=16
PROD_ALLOWED_CODECS="h264"
PROD_MAX_PROMPTS=2
case "${WAN_TEST_MODE}" in
  0)
    for variable in WAN_MODEL_DIR WAN_MODEL_REPO_ID WAN_MODEL_SOURCE WAN_MODEL_REVISION \
        WAN_PYTHON_BIN WAN_TORCHRUN_BIN WAN_PROMPTS_FILE WAN_NUM_GPUS WAN_SIZE \
        WAN_SAMPLE_STEPS WAN_FRAME_NUM WAN_EXPECTED_FPS WAN_ALLOWED_CODECS WAN_MAX_PROMPTS; do
      if [[ -v "${variable}" ]]; then
        echo "production model path override is forbidden; production smoke contract override is forbidden: ${variable}" >&2
        exit 2
      fi
    done
    WAN_MODEL_DIR="${PROD_MODEL_LINK}"
    MODEL_REPO_ID="${PROD_MODEL_REPO_ID}"
    MODEL_SOURCE="${PROD_MODEL_SOURCE}"
    MODEL_REVISION="${PROD_MODEL_REVISION}"
    PYTHON_BIN="${PROD_PYTHON_BIN}"
    TORCHRUN_BIN="${PROD_TORCHRUN_BIN}"
    PROMPTS_FILE="${WAN_REPO_DIR}/${PROD_PROMPT_FILE_RELATIVE}"
    NUM_GPUS="${PROD_NUM_GPUS}"
    SIZE="${PROD_SIZE}"
    SAMPLE_STEPS="${PROD_SAMPLE_STEPS}"
    FRAME_NUM="${PROD_FRAME_NUM}"
    EXPECTED_FPS="${PROD_EXPECTED_FPS}"
    ALLOWED_CODECS="${PROD_ALLOWED_CODECS}"
    MAX_PROMPTS="${PROD_MAX_PROMPTS}"
    ;;
  1)
    : "${WAN_MODEL_DIR:?WAN_TEST_MODE=1 requires WAN_MODEL_DIR}"
    MODEL_REPO_ID="${WAN_MODEL_REPO_ID:-${PROD_MODEL_REPO_ID}}"
    MODEL_SOURCE="${WAN_MODEL_SOURCE:-${PROD_MODEL_SOURCE}}"
    MODEL_REVISION="${WAN_MODEL_REVISION:-${PROD_MODEL_REVISION}}"
    PYTHON_BIN="${WAN_PYTHON_BIN:-python}"
    TORCHRUN_BIN="${WAN_TORCHRUN_BIN:-torchrun}"
    PROMPTS_FILE="${WAN_PROMPTS_FILE:-${WAN_REPO_DIR}/${PROD_PROMPT_FILE_RELATIVE}}"
    NUM_GPUS="${WAN_NUM_GPUS:-8}"
    SIZE="${WAN_SIZE:-832*480}"
    SAMPLE_STEPS="${WAN_SAMPLE_STEPS:-40}"
    FRAME_NUM="${WAN_FRAME_NUM:-81}"
    EXPECTED_FPS="${WAN_EXPECTED_FPS:-16}"
    ALLOWED_CODECS="${WAN_ALLOWED_CODECS:-h264}"
    MAX_PROMPTS="${WAN_MAX_PROMPTS:-2}"
    ;;
  *)
    echo "WAN_TEST_MODE must be 0 or 1" >&2
    exit 2
    ;;
esac

canonicalize_path() {
  command -v realpath >/dev/null 2>&1 || {
    echo "GNU realpath is required before any test-mode filesystem access" >&2
    exit 2
  }
  realpath -m -- "$1"
}

if [[ "${WAN_TEST_MODE}" == "1" ]]; then
  PROD_WEIGHT_ROOT_CANON="$(canonicalize_path "${PROD_WEIGHT_ROOT}")"
  PROD_WEIGHT_TARGET_CANON="$(canonicalize_path "${PROD_WEIGHT_TARGET}")"
  PROD_MODEL_LINK_CANON="$(canonicalize_path "${PROD_MODEL_LINK}")"
  PROD_CONTAINER_TARGET_CANON="$(canonicalize_path "${PROD_CONTAINER_TARGET}")"
  reject_production_path() {
    local label="$1" value="$2" canonical
    canonical="$(canonicalize_path "${value}")"
    case "${canonical}" in
      "${PROD_WEIGHT_ROOT_CANON}"|"${PROD_WEIGHT_ROOT_CANON}"/*|"${PROD_WEIGHT_TARGET_CANON}"|"${PROD_WEIGHT_TARGET_CANON}"/*|"${PROD_MODEL_LINK_CANON}"|"${PROD_MODEL_LINK_CANON}"/*|"${PROD_CONTAINER_TARGET_CANON}"|"${PROD_CONTAINER_TARGET_CANON}"/*)
        echo "test model path may not touch the production Wan2.2 link; test path would touch production ${label}: ${value} -> ${canonical}" >&2
        exit 2
        ;;
    esac
  }
  reject_production_path model_dir "${WAN_MODEL_DIR}"
  reject_production_path run_root "${WAN_RUN_ROOT}"
  reject_production_path repo "${WAN_REPO_DIR}"
else
  [[ "${WAN_REPO_DIR}" == "${PROD_REPO_DIR}" ]] || {
    echo "production WAN_REPO_DIR must equal ${PROD_REPO_DIR}" >&2
    exit 2
  }
  PROD_RUN_ROOT_BASE_CANON="$(canonicalize_path "${PROD_RUN_ROOT_BASE}")"
  PROD_RUN_ROOT_CANON="$(canonicalize_path "${WAN_RUN_ROOT}")"
  [[ "${PROD_RUN_ROOT_CANON}" != "${PROD_RUN_ROOT_BASE_CANON}" &&
     "${PROD_RUN_ROOT_CANON}" == "${PROD_RUN_ROOT_BASE_CANON}"/* ]] || {
    echo "production WAN_RUN_ROOT must be a unique child of ${PROD_RUN_ROOT_BASE}" >&2
    exit 2
  }
fi

RUN_ID="${WAN_RUN_ID:-wan_t2v_smoke_$(date -u +%Y%m%dT%H%M%SZ)}"
HOST_NAME="${WAN_HOST_NAME:-$(hostname)}"
CONTAINER_NAME="${WAN_CONTAINER_NAME:-}"

if [[ "${WAN_TEST_MODE}" == "1" ]]; then
  reject_production_path prompts "${PROMPTS_FILE}"
fi

require_command() {
  local command_name="$1"
  if [[ "${command_name}" == */* ]]; then
    [[ -x "${command_name}" ]] || {
      echo "required executable is missing or not executable: ${command_name}" >&2
      exit 2
    }
  else
    command -v "${command_name}" >/dev/null 2>&1 || {
      echo "required command is not on PATH: ${command_name}" >&2
      exit 2
    }
  fi
}

[[ -d "${WAN_REPO_DIR}" && -f "${WAN_REPO_DIR}/generate.py" ]] || {
  echo "invalid Wan2.2 repository: ${WAN_REPO_DIR}" >&2
  exit 2
}
[[ -d "${WAN_MODEL_DIR}" ]] || {
  echo "model directory is missing: ${WAN_MODEL_DIR}" >&2
  exit 2
}

verify_fixed_model_contract() {
  local identity="${WAN_MODEL_DIR}/.wan22_t2v_a14b.identity"
  local complete="${WAN_MODEL_DIR}/.wan22_t2v_a14b.complete"
  local inventory="${WAN_MODEL_DIR}/.wan22_t2v_a14b.inventory.json"
  local inventory_hash
  for path in "${identity}" "${complete}" "${inventory}"; do
    [[ -f "${path}" && ! -L "${path}" ]] || {
      echo "production model contract file is missing or symlinked: ${path}" >&2
      return 1
    }
  done
  for field in \
      "source=${PROD_MODEL_SOURCE}" \
      "model_id=${PROD_MODEL_REPO_ID}" \
      "revision=${PROD_MODEL_REVISION}" \
      "manifest_sha256=${PROD_MANIFEST_SHA256}" \
      "required_files_sha256=${PROD_MANIFEST_SHA256}" \
      "expected_file_count=${PROD_FILE_COUNT}" \
      "expected_total_bytes=${PROD_TOTAL_BYTES}" \
      "audit_sha256=${PROD_AUDIT_SHA256}"; do
    grep -Fxq "${field}" "${identity}" || {
      echo "production identity contract mismatch: ${field}" >&2
      return 1
    }
    grep -Fxq "${field}" "${complete}" || {
      echo "production complete contract mismatch: ${field}" >&2
      return 1
    }
  done
  inventory_hash="$(sha256sum "${inventory}" | awk '{print $1}')"
  grep -Fxq "inventory_sha256=${inventory_hash}" "${complete}" || {
    echo "production inventory hash mismatch" >&2
    return 1
  }
}

if [[ "${WAN_TEST_MODE}" == "0" ]]; then
  [[ -L "${WAN_MODEL_DIR}" && "$(readlink -- "${WAN_MODEL_DIR}")" == "${PROD_CONTAINER_TARGET}" ]] || {
    echo "production model path is not the audited public symlink: ${WAN_MODEL_DIR}" >&2
    exit 2
  }
  verify_fixed_model_contract || exit 2
fi
require_command "${PYTHON_BIN}"
require_command "${TORCHRUN_BIN}"
require_command ffprobe
require_command realpath
if [[ "${WAN_TEST_MODE}" == "0" ]]; then
  require_command readlink
fi
"${PYTHON_BIN}" -c 'import einops' >/dev/null 2>&1 || {
  echo "required dependency is missing: einops (install from requirements.txt)" >&2
  exit 2
}
"${PYTHON_BIN}" -c 'import decord' >/dev/null 2>&1 || {
  echo "required dependency is missing: decord (install from requirements.txt)" >&2
  exit 2
}
[[ "${NUM_GPUS}" =~ ^[1-9][0-9]*$ ]] || {
  echo "WAN_NUM_GPUS must be a positive integer: ${NUM_GPUS}" >&2
  exit 2
}
[[ "${MAX_PROMPTS}" =~ ^[1-9][0-9]*$ ]] || {
  echo "WAN_MAX_PROMPTS must be a positive integer: ${MAX_PROMPTS}" >&2
  exit 2
}
[[ "${EXPECTED_FPS}" =~ ^[1-9][0-9]*([.][0-9]+)?$ ]] || {
  echo "WAN_EXPECTED_FPS must be a positive number: ${EXPECTED_FPS}" >&2
  exit 2
}
[[ -n "${ALLOWED_CODECS//,/}" ]] || {
  echo "WAN_ALLOWED_CODECS must contain at least one codec" >&2
  exit 2
}
[[ -f "${WAN_REPO_DIR}/tools/validate_wan_smoke_output.py" ]] || {
  echo "output validator is missing from the source checkout" >&2
  exit 2
}
if [[ -e "${WAN_RUN_ROOT}" ]]; then
  echo "refusing to reuse an existing run root: ${WAN_RUN_ROOT}" >&2
  exit 2
fi

git_repo() {
  (cd "${WAN_REPO_DIR}" && git "$@")
}

mkdir -p "${WAN_RUN_ROOT}/logs" "${WAN_RUN_ROOT}/videos" "${WAN_RUN_ROOT}/metadata"
STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMMAND_LOG="${WAN_RUN_ROOT}/command.log"
STATUS_LOG="${WAN_RUN_ROOT}/status.tsv"

git_repo rev-parse HEAD > "${WAN_RUN_ROOT}/source_head.txt"
git_repo status --short > "${WAN_RUN_ROOT}/source_status.txt"
printf 'run_id\t%s\nstarted_utc\t%s\n' "${RUN_ID}" "${STARTED_UTC}" > "${WAN_RUN_ROOT}/run_identity.tsv"

if [[ ! -s "${PROMPTS_FILE}" ]]; then
  echo "prompt file missing or empty: ${PROMPTS_FILE}" >&2
  exit 2
fi

mapfile -t PROMPT_ROWS < <("${PYTHON_BIN}" - "${PROMPTS_FILE}" "${MAX_PROMPTS}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
limit = int(sys.argv[2])
rows = []
seen_ids = set()
for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    fields = line.split("\t", 2)
    if len(fields) != 3 or not fields[0] or not fields[1].isdigit() or not fields[2]:
        raise SystemExit(f"invalid prompt row {path}:{number}")
    prompt_id = fields[0]
    if prompt_id in {".", ".."} or not __import__("re").fullmatch(r"[A-Za-z0-9._-]+", prompt_id):
        raise SystemExit(f"invalid prompt id {prompt_id!r} at {path}:{number}")
    if prompt_id in seen_ids:
        raise SystemExit(f"duplicate prompt id {prompt_id!r} at {path}:{number}")
    seen_ids.add(prompt_id)
    rows.append(fields)
if not rows:
    raise SystemExit(f"no prompt rows in {path}")
for row in rows[:limit]:
    print("\t".join(row))
PY
)

if [[ "${#PROMPT_ROWS[@]}" -eq 0 ]]; then
  echo "no prompts selected" >&2
  exit 2
fi
if [[ "${WAN_TEST_MODE}" == "0" ]]; then
  [[ "${PROMPTS_FILE}" == "${WAN_REPO_DIR}/${PROD_PROMPT_FILE_RELATIVE}" ]] || {
    echo "production prompt file is not the fixed official prompt file" >&2
    exit 2
  }
  actual_prompt_hash="$(sha256sum -- "${PROMPTS_FILE}" | awk '{print $1}')"
  [[ "${actual_prompt_hash}" == "${PROD_PROMPTS_SHA256}" ]] || {
    echo "production prompt file hash mismatch" >&2
    exit 2
  }
  [[ "${#PROMPT_ROWS[@]}" -eq "${PROD_MAX_PROMPTS}" ]] || {
    echo "production prompt selection count mismatch" >&2
    exit 2
  }
  selected_prompt_hash="$(printf '%s\n' "${PROMPT_ROWS[@]}" | sha256sum | awk '{print $1}')"
  [[ "${selected_prompt_hash}" == "${PROD_SELECTED_PROMPTS_SHA256}" ]] || {
    echo "production selected prompt hash mismatch" >&2
    exit 2
  }
  [[ "${PROMPT_ROWS[0]}" == motion_01$'\t'401$'\t'* &&
     "${PROMPT_ROWS[1]}" == physics_02$'\t'402$'\t'* ]] || {
    echo "production prompt IDs/seeds are not the fixed first two rows" >&2
    exit 2
  }
fi
SELECTED_PROMPTS_FILE="${WAN_RUN_ROOT}/selected_prompts.tsv"
printf '%s\n' "${PROMPT_ROWS[@]}" > "${SELECTED_PROMPTS_FILE}"

resolve_under() {
  local root="$1"
  local candidate="$2"
  local resolved_root
  local resolved_candidate
  resolved_root="$(realpath -e -- "${root}")"
  resolved_candidate="$(realpath -m -- "${candidate}")"
  case "${resolved_candidate}" in
    "${resolved_root}"/*) printf '%s' "${resolved_candidate}" ;;
    *) echo "resolved path escapes ${resolved_root}: ${resolved_candidate}" >&2; exit 2 ;;
  esac
}

: > "${STATUS_LOG}"
: > "${STATUS_LOG}.result"
: > "${COMMAND_LOG}"
overall_rc=0
for row in "${PROMPT_ROWS[@]}"; do
  IFS=$'\t' read -r prompt_id seed prompt <<< "${row}"
  output_file="$(resolve_under "${WAN_RUN_ROOT}/videos" "${WAN_RUN_ROOT}/videos/${prompt_id}.mp4")"
  log_file="$(resolve_under "${WAN_RUN_ROOT}/logs" "${WAN_RUN_ROOT}/logs/${prompt_id}.log")"
  metadata_file="$(resolve_under "${WAN_RUN_ROOT}/metadata" "${WAN_RUN_ROOT}/metadata/${prompt_id}.json")"
  cmd=(
    "${TORCHRUN_BIN}" "--nproc_per_node=${NUM_GPUS}"
    "${WAN_REPO_DIR}/generate.py" --task t2v-A14B --size "${SIZE}"
    --ckpt_dir "${WAN_MODEL_DIR}" --dit_fsdp --t5_fsdp
    --ulysses_size "${NUM_GPUS}" --base_seed "${seed}"
    --sample_steps "${SAMPLE_STEPS}" --frame_num "${FRAME_NUM}"
    --save_file "${output_file}" --prompt "${prompt}"
  )
  printf '%q ' "${cmd[@]}" >> "${COMMAND_LOG}"
  printf '\n' >> "${COMMAND_LOG}"
  printf '%s\t%s\t%s\n' "${prompt_id}" "${seed}" "${output_file}" >> "${STATUS_LOG}"
  set +e
  "${cmd[@]}" > "${log_file}" 2>&1
  rc=$?
  set -e
  printf '%s\t%s\t%s\n' "${prompt_id}" "${rc}" "${output_file}" >> "${STATUS_LOG}.result"
  if [[ "${rc}" -ne 0 ]]; then
    overall_rc="${rc}"
    continue
  fi
  if [[ ! -s "${output_file}" ]]; then
    overall_rc=1
    printf 'missing_or_empty_output\n' >> "${log_file}"
    continue
  fi
  if ! ffprobe -v error -count_frames -show_entries 'format=format_name,duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames,nb_read_frames' -of json "${output_file}" > "${metadata_file}"; then
    overall_rc=1
    printf 'ffprobe_failed\n' >> "${log_file}"
    continue
  fi
  if ! "${PYTHON_BIN}" "${WAN_REPO_DIR}/tools/validate_wan_smoke_output.py" \
      --video "${output_file}" --metadata "${metadata_file}" \
      --size "${SIZE}" --frame-num "${FRAME_NUM}" \
      --expected-fps "${EXPECTED_FPS}" --allowed-codecs "${ALLOWED_CODECS}" \
      --write-normalized >> "${log_file}" 2>&1; then
    overall_rc=1
    printf 'output_validation_failed\n' >> "${log_file}"
  fi
done

ENDED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
manifest_args=(
  --output "${WAN_RUN_ROOT}/manifest.json" --repo "${WAN_REPO_DIR}"
  --model-dir "${WAN_MODEL_DIR}" --prompts "${SELECTED_PROMPTS_FILE}"
  --model-repo-id "${MODEL_REPO_ID}"
  --model-revision "${MODEL_REVISION}"
  --model-source "${MODEL_SOURCE}"
  --run-id "${RUN_ID}" --run-root "${WAN_RUN_ROOT}"
  --status "$([[ "${overall_rc}" -eq 0 ]] && echo completed || echo failed)"
  --exit-code "${overall_rc}" --started-utc "${STARTED_UTC}"
  --ended-utc "${ENDED_UTC}" --host "${HOST_NAME}"
  --container "${CONTAINER_NAME}" --environment-python "${PYTHON_BIN}"
  --torchrun "${TORCHRUN_BIN}" --num-gpus "${NUM_GPUS}"
  --command-log "${COMMAND_LOG}"
  --size "${SIZE}" --sample-steps "${SAMPLE_STEPS}" --frame-num "${FRAME_NUM}"
  --expected-fps "${EXPECTED_FPS}" --allowed-codecs "${ALLOWED_CODECS}"
  --test-mode "${WAN_TEST_MODE}" --max-prompts "${MAX_PROMPTS}"
)
for row in "${PROMPT_ROWS[@]}"; do
  prompt_id="${row%%$'\t'*}"
  manifest_args+=(--selected-prompt-id "${prompt_id}")
  manifest_args+=(--output-file "${WAN_RUN_ROOT}/videos/${prompt_id}.mp4")
done
"${PYTHON_BIN}" "${WAN_REPO_DIR}/tools/write_wan_smoke_manifest.py" "${manifest_args[@]}"
printf 'ended_utc\t%s\nexit_code\t%s\n' "${ENDED_UTC}" "${overall_rc}" >> "${WAN_RUN_ROOT}/run_identity.tsv"
exit "${overall_rc}"
