#!/usr/bin/env bash
set -Eeuo pipefail

RUN_ID="${WAN22_RUN_ID:-wan22_env_pack_$(date -u +%Y%m%dT%H%M%SZ)_$$}"
SETUP_ROOT="${WAN22_SETUP_ROOT:-/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_setup}"
LOG_DIR="${SETUP_ROOT}/logs"
TMP_DIR="${SETUP_ROOT}/tmp"
LOCK_DIR="${SETUP_ROOT}/.env-pack.lock"
SOURCE="${WAN22_SOURCE_ENV:-/public/wangwx/softwares/new_Anaconda3/Anaconda3/envs/Wan}"
FIXED_ENV="${WAN22_FIXED_ENV:-/public/xbw/conda-envs/wan22-t2v-a14b}"
VERSIONED_ENV="${WAN22_VERSIONED_ENV:-/public/xbw/conda-envs/wan22-t2v-a14b.${RUN_ID}}"
TEMP_ENV="${WAN22_TEMP_ENV:-/public/xbw/conda-envs/wan22-t2v-a14b.tmp-${RUN_ID}}"
CONDA_PACK="${WAN22_CONDA_PACK:-/public/zlzhu/LifeNet/anaconda3/bin/conda-pack}"
ARCHIVE_PART="${TMP_DIR}/wan-env-${RUN_ID}.tar.gz.part"
LOG="${LOG_DIR}/${RUN_ID}.log"
IDENTITY="${LOG_DIR}/${RUN_ID}.identity"
EXIT_MARKER="${LOG_DIR}/${RUN_ID}.exit"
BOOT_DIR="${SETUP_ROOT}/.run-markers"
BOOT_EXIT="${BOOT_DIR}/${RUN_ID}.exit"
BOOT_IDENTITY="${BOOT_DIR}/${RUN_ID}.identity"
BOOT_LOG="${BOOT_DIR}/${RUN_ID}.bootstrap.log"
LOCK_HELD=0
VERSIONED_CREATED=0
START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

[[ "${RUN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "unsafe RUN_ID: ${RUN_ID}" >&2
  exit 2
}
mkdir -p "${SETUP_ROOT}" "${BOOT_DIR}"
for path in "${BOOT_EXIT}" "${BOOT_IDENTITY}" "${BOOT_LOG}"; do
  [[ ! -e "${path}" ]] || { echo "bootstrap artifact already exists: ${path}" >&2; exit 2; }
done
: >"${BOOT_EXIT}" || { echo "cannot create bootstrap exit marker: ${BOOT_EXIT}" >&2; exit 2; }
: >"${BOOT_IDENTITY}" || { echo "cannot create bootstrap identity: ${BOOT_IDENTITY}" >&2; exit 2; }
: >"${BOOT_LOG}" || { echo "cannot create bootstrap log: ${BOOT_LOG}" >&2; exit 2; }
printf 'run_id=%s\nstart_utc=%s\nsetup_root=%s\n' "${RUN_ID}" "${START_UTC}" "${SETUP_ROOT}" >"${BOOT_IDENTITY}"
bootstrap_err() {
  printf 'bootstrap_error_utc=%s\nbootstrap_error_rc=%s\nbootstrap_error_line=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >>"${BOOT_LOG}" 2>/dev/null || true
}
bootstrap_exit() {
  local rc="$?"
  trap - ERR EXIT
  printf 'run_id=%s\nstart_utc=%s\nend_utc=%s\nexit_code=%s\n' \
    "${RUN_ID}" "${START_UTC}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${rc}" >"${BOOT_EXIT}" 2>/dev/null || \
    printf 'bootstrap exit_code=%s\n' "${rc}" >&2
  exit "${rc}"
}
trap 'bootstrap_err "$?" "$LINENO"' ERR
trap bootstrap_exit EXIT

mkdir -p "${LOG_DIR}" "${TMP_DIR}"
for path in "${LOG}" "${IDENTITY}" "${EXIT_MARKER}"; do
  [[ ! -e "${path}" ]] || {
    echo "run artifact already exists; refusing overwrite: ${path}" >&2
    exit 2
  }
done
: >"${LOG}"
: >"${IDENTITY}"
exec >>"${LOG}" 2>&1

cat >"${IDENTITY}" <<EOF
run_id=${RUN_ID}
start_utc=${START_UTC}
source=${SOURCE}
archive_part=${ARCHIVE_PART}
versioned_env=${VERSIONED_ENV}
temporary_env=${TEMP_ENV}
fixed_env_link=${FIXED_ENV}
conda_pack=${CONDA_PACK}
EOF
trap - ERR EXIT

on_err() {
  local rc="$1" line="$2"
  printf 'error_utc=%s\nerror_rc=%s\nerror_line=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${rc}" "${line}" >>"${LOG}"
}

cleanup_owned() {
  local part_guard="${SETUP_ROOT}/tmp/wan-env-${RUN_ID}.tar.gz.part"
  local env_guard="/public/xbw/conda-envs/wan22-t2v-a14b.tmp-${RUN_ID}"
  if [[ "${ARCHIVE_PART}" == "${part_guard}" && -e "${ARCHIVE_PART}" ]]; then
    rm -f -- "${ARCHIVE_PART}" || true
  fi
  if [[ "${VERSIONED_CREATED}" -eq 1 && "${TEMP_ENV}" == "${env_guard}" \
        && -d "${TEMP_ENV}" && ! -L "${TEMP_ENV}" ]]; then
    rm -rf -- "${TEMP_ENV}" || true
  fi
}

release_lock() {
  local expected_lock="${SETUP_ROOT}/.env-pack.lock"
  local expected_owner="${SETUP_ROOT}/.env-pack.lock/owner"
  if [[ "${LOCK_HELD}" -eq 1 && "${LOCK_DIR}" == "${expected_lock}" \
        && "${LOCK_DIR}/owner" == "${expected_owner}" && -d "${LOCK_DIR}" ]]; then
    if [[ -f "${expected_owner}" ]]; then
      rm -f -- "${expected_owner}" || true
    fi
    rmdir -- "${LOCK_DIR}" || true
  fi
}

on_exit() {
  local rc="$?"
  trap - ERR EXIT
  if [[ "${rc}" -ne 0 ]]; then
    cleanup_owned
  fi
  printf 'run_id=%s\nstart_utc=%s\nend_utc=%s\nexit_code=%s\n' \
    "${RUN_ID}" "${START_UTC}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${rc}" >"${EXIT_MARKER}"
  printf 'run_id=%s\nstart_utc=%s\nend_utc=%s\nexit_code=%s\n' \
    "${RUN_ID}" "${START_UTC}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${rc}" >"${BOOT_EXIT}" || true
  release_lock
  exit "${rc}"
}
trap 'on_err "$?" "$LINENO"' ERR
trap on_exit EXIT

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "environment pack lock is held: ${LOCK_DIR}"
  exit 3
fi
LOCK_HELD=1
printf 'lock_owner_run_id=%s\nlock_pid=%s\n' "${RUN_ID}" "$$" >"${LOCK_DIR}/owner"

if [[ ! -d "${SOURCE}" ]]; then
  echo "source environment missing: ${SOURCE}"
  exit 2
fi
if [[ ! -x "${CONDA_PACK}" ]]; then
  echo "conda-pack executable missing: ${CONDA_PACK}"
  exit 2
fi
if [[ -e "${ARCHIVE_PART}" || -L "${ARCHIVE_PART}" ]]; then
  echo "archive part already exists; refusing overwrite: ${ARCHIVE_PART}"
  exit 2
fi
if [[ -e "${VERSIONED_ENV}" || -L "${VERSIONED_ENV}" ]]; then
  echo "versioned environment already exists; refusing overwrite: ${VERSIONED_ENV}"
  exit 2
fi
if [[ -e "${TEMP_ENV}" || -L "${TEMP_ENV}" ]]; then
  echo "temporary environment already exists; refusing overwrite: ${TEMP_ENV}"
  exit 2
fi
if [[ -e "${FIXED_ENV}" || -L "${FIXED_ENV}" ]]; then
  echo "fixed environment path already exists; refusing replace: ${FIXED_ENV}"
  exit 2
fi

echo "pack_start_utc=${START_UTC}"
"${CONDA_PACK}" -p "${SOURCE}" -o "${ARCHIVE_PART}" --format tar.gz
[[ -s "${ARCHIVE_PART}" ]] || {
  echo "archive part missing or empty after conda-pack"
  exit 1
}
echo "pack_end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir "${TEMP_ENV}"
VERSIONED_CREATED=1
tar -xzf "${ARCHIVE_PART}" -C "${TEMP_ENV}"
echo "extract_end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ -x "${TEMP_ENV}/bin/conda-unpack" ]]; then
  "${TEMP_ENV}/bin/conda-unpack"
elif [[ -f "${TEMP_ENV}/bin/conda-unpack" && -x "${TEMP_ENV}/bin/python" ]]; then
  "${TEMP_ENV}/bin/python" "${TEMP_ENV}/bin/conda-unpack"
else
  echo "conda-unpack missing from packed environment"
  exit 1
fi

CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.1}"
export CUDA_HOME
export LD_LIBRARY_PATH="${CUDA_HOME}/extras/CUPTI/lib64:${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"
"${TEMP_ENV}/bin/python" -c 'import sys; print(sys.version)'
"${TEMP_ENV}/bin/python" -c 'import torch; print(torch.__version__)'
EINOPS_VERSION="$("${TEMP_ENV}/bin/python" -c 'import einops, importlib.metadata; print(importlib.metadata.version("einops"))')"
printf 'einops_version=%s\n' "${EINOPS_VERSION}" >>"${IDENTITY}"
echo "einops_version=${EINOPS_VERSION}"
DECORD_PYTHON="${TEMP_ENV}/bin/python"
DECORD_VERSION="$("${DECORD_PYTHON}" -c 'import decord, importlib.metadata; print(importlib.metadata.version("decord"))')"
printf 'decord_version=%s\n' "${DECORD_VERSION}" >>"${IDENTITY}"
echo "decord_version=${DECORD_VERSION}"
echo "basic_import_end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -e "${FIXED_ENV}" || -L "${FIXED_ENV}" ]]; then
  echo "fixed environment path appeared during build; refusing replace: ${FIXED_ENV}"
  exit 2
fi
mv -- "${TEMP_ENV}" "${VERSIONED_ENV}"
VERSIONED_CREATED=0
ln -s "${VERSIONED_ENV}" "${FIXED_ENV}"
echo "published_fixed_env=$(readlink "${FIXED_ENV}")"
echo "environment_publish_end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit 0
