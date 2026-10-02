#!/usr/bin/env bash
set -Eeuo pipefail

# Production is deliberately not configurable.  The only way to exercise
# this wrapper with temporary paths is WAN22_TEST_MODE=1; this prevents a
# typo in a test from touching the real model directory or public link.
PROD_ROOT="/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_weights"
PROD_TARGET="${PROD_ROOT}/Wan2.2-T2V-A14B"
PROD_LINK="/public/xbw/Wan2.2-T2V-A14B"
PROD_CONTAINER_TARGET="/storage-root/9950backfile/liujing/zkliu/interleaved/wan22_t2v_a14b_weights/Wan2.2-T2V-A14B"
PROD_SOURCE_ENV="/public/wangwx/softwares/new_Anaconda3/Anaconda3/envs/wan22"
PROD_MODELSCOPE_BIN="/public/wangwx/softwares/new_Anaconda3/Anaconda3/bin/modelscope"
PROD_REQUIRED_FILES="/public/xbw/Wan2.2/tools/wan22_t2v_a14b_modelscope_required_files.tsv"
PROD_SNAPSHOT="/public/xbw/Wan2.2/tools/wan22_modelscope_api_snapshot.json"
PROD_SNAPSHOT_PY="/public/xbw/Wan2.2/tools/wan22_modelscope_snapshot.py"
PROD_AUDIT_PY="/public/xbw/Wan2.2/tools/audit_wan22_required_files.py"
PROD_MANIFEST_SHA256="3cfb749560e87a7b1cc2faa14cbb59860d66600447014436ddb1625dba1dbe1f"
# Updated whenever audit_wan22_required_files.py changes.  This is checked in
# production so the manifest cannot be paired with an unreviewed auditor.
PROD_AUDIT_SHA256="1ce45b58c4de731e53814cd1c7c50b9158e078de067165bf7b1b8cb41e597979"
PROD_SNAPSHOT_SHA256="f1291e99b1ba101ddcd550bceb7f4fa84a6a1217cb420f50894e77e7319bc03b"
PROD_SNAPSHOT_PY_SHA256="be7300caf97ac6150c1a7fe9e50326b0fe1ede0e6f743763af59d8c64c1014c2"
PROD_FILE_COUNT=32
PROD_TOTAL_BYTES=126201624156
MODEL_ID="Wan-AI/Wan2.2-T2V-A14B"

TEST_MODE="${WAN22_TEST_MODE:-0}"
case "${TEST_MODE}" in
  0) ;;
  1) ;;
  *) echo "WAN22_TEST_MODE must be 0 or 1" >&2; exit 2 ;;
esac

if [[ "${TEST_MODE}" == "1" ]]; then
  : "${WAN22_WEIGHTS_ROOT:?test mode requires WAN22_WEIGHTS_ROOT}"
  : "${WAN22_WEIGHTS_TARGET:?test mode requires WAN22_WEIGHTS_TARGET}"
  : "${WAN22_PUBLIC_LINK:?test mode requires WAN22_PUBLIC_LINK}"
  : "${WAN22_CONTAINER_TARGET:?test mode requires WAN22_CONTAINER_TARGET}"
  : "${WAN22_SOURCE_ENV:?test mode requires WAN22_SOURCE_ENV}"
  : "${WAN22_REQUIRED_FILES:?test mode requires WAN22_REQUIRED_FILES}"
  : "${WAN22_AUDIT_PY:?test mode requires WAN22_AUDIT_PY}"
  ROOT="${WAN22_WEIGHTS_ROOT}"
  TARGET="${WAN22_WEIGHTS_TARGET}"
  LINK="${WAN22_PUBLIC_LINK}"
  CONTAINER_TARGET="${WAN22_CONTAINER_TARGET}"
  SOURCE_ENV="${WAN22_SOURCE_ENV}"
  REQUIRED_FILES="${WAN22_REQUIRED_FILES}"
  AUDIT_PY="${WAN22_AUDIT_PY}"
  MODELSCOPE_BIN="${WAN22_MODELSCOPE_BIN:-}"
  DOWNLOAD_SOURCE="${WAN22_DOWNLOAD_SOURCE:-modelscope}"
  REVISION="${WAN22_MODEL_REVISION:-master}"
  SNAPSHOT="${WAN22_SNAPSHOT:-}"
  SNAPSHOT_PY="${WAN22_SNAPSHOT_PY:-}"
else
  for variable in WAN22_WEIGHTS_ROOT WAN22_WEIGHTS_TARGET WAN22_PUBLIC_LINK \
      WAN22_CONTAINER_TARGET WAN22_SOURCE_ENV WAN22_REQUIRED_FILES WAN22_AUDIT_PY \
      WAN22_MODELSCOPE_BIN WAN22_SNAPSHOT WAN22_SNAPSHOT_PY WAN22_DOWNLOAD_SOURCE \
      WAN22_MODEL_REVISION; do
    if [[ -v "${variable}" ]]; then
      echo "production path/source override is forbidden: ${variable}" >&2
      exit 2
    fi
  done
  ROOT="${PROD_ROOT}"
  TARGET="${PROD_TARGET}"
  LINK="${PROD_LINK}"
  CONTAINER_TARGET="${PROD_CONTAINER_TARGET}"
  SOURCE_ENV="${PROD_SOURCE_ENV}"
  REQUIRED_FILES="${PROD_REQUIRED_FILES}"
  AUDIT_PY="${PROD_AUDIT_PY}"
  MODELSCOPE_BIN="${PROD_MODELSCOPE_BIN}"
  SNAPSHOT="${PROD_SNAPSHOT}"
  SNAPSHOT_PY="${PROD_SNAPSHOT_PY}"
  DOWNLOAD_SOURCE="modelscope"
  REVISION="master"
fi

canonicalize_path() {
  command -v realpath >/dev/null 2>&1 || {
    echo "GNU realpath is required before any test-mode filesystem access" >&2
    exit 2
  }
  realpath -m -- "$1"
}

PROD_ROOT_CANON="$(canonicalize_path "${PROD_ROOT}")"
PROD_TARGET_CANON="$(canonicalize_path "${PROD_TARGET}")"
PROD_LINK_CANON="$(canonicalize_path "${PROD_LINK}")"
PROD_CONTAINER_TARGET_CANON="$(canonicalize_path "${PROD_CONTAINER_TARGET}")"
PROD_SOURCE_ENV_CANON="$(canonicalize_path "${PROD_SOURCE_ENV}")"
PROD_MODELSCOPE_BIN_CANON="$(canonicalize_path "${PROD_MODELSCOPE_BIN}")"
PROD_REQUIRED_FILES_CANON="$(canonicalize_path "${PROD_REQUIRED_FILES}")"
PROD_AUDIT_PY_CANON="$(canonicalize_path "${PROD_AUDIT_PY}")"
PROD_SNAPSHOT_CANON="$(canonicalize_path "${PROD_SNAPSHOT}")"
PROD_SNAPSHOT_PY_CANON="$(canonicalize_path "${PROD_SNAPSHOT_PY}")"

reject_production_path() {
  local label="$1" value="$2" canonical
  canonical="$(canonicalize_path "${value}")"
  case "${canonical}" in
    "${PROD_ROOT_CANON}"|"${PROD_ROOT_CANON}"/*|"${PROD_TARGET_CANON}"|"${PROD_TARGET_CANON}"/*|"${PROD_LINK_CANON}"|"${PROD_LINK_CANON}"/*|"${PROD_CONTAINER_TARGET_CANON}"|"${PROD_CONTAINER_TARGET_CANON}"/*|"${PROD_SOURCE_ENV_CANON}"|"${PROD_SOURCE_ENV_CANON}"/*|"${PROD_MODELSCOPE_BIN_CANON}"|"${PROD_MODELSCOPE_BIN_CANON}"/*|"${PROD_REQUIRED_FILES_CANON}"|"${PROD_REQUIRED_FILES_CANON}"/*|"${PROD_AUDIT_PY_CANON}"|"${PROD_AUDIT_PY_CANON}"/*|"${PROD_SNAPSHOT_CANON}"|"${PROD_SNAPSHOT_CANON}"/*|"${PROD_SNAPSHOT_PY_CANON}"|"${PROD_SNAPSHOT_PY_CANON}"/*)
      echo "test path would touch production ${label}: ${value} -> ${canonical}" >&2
      exit 2
      ;;
  esac
}
if [[ "${TEST_MODE}" == "1" ]]; then
  reject_production_path root "${ROOT}"
  reject_production_path target "${TARGET}"
  reject_production_path public_link "${LINK}"
  reject_production_path container_target "${CONTAINER_TARGET}"
  reject_production_path source_env "${SOURCE_ENV}"
  [[ -z "${MODELSCOPE_BIN}" ]] || reject_production_path modelscope_bin "${MODELSCOPE_BIN}"
  reject_production_path required_files "${REQUIRED_FILES}"
  reject_production_path audit "${AUDIT_PY}"
  [[ -z "${SNAPSHOT}" ]] || reject_production_path snapshot "${SNAPSHOT}"
  [[ -z "${SNAPSHOT_PY}" ]] || reject_production_path snapshot_verifier "${SNAPSHOT_PY}"
  if [[ "${DOWNLOAD_SOURCE}" == "modelscope" ]]; then
    [[ -n "${MODELSCOPE_BIN}" ]] || {
      echo "test ModelScope source requires explicit WAN22_MODELSCOPE_BIN" >&2
      exit 2
    }
    [[ "${MODELSCOPE_BIN}" == /* && -x "${MODELSCOPE_BIN}" && ! -L "${MODELSCOPE_BIN}" ]] || {
      echo "test WAN22_MODELSCOPE_BIN must be an executable absolute path" >&2
      exit 2
    }
  fi
fi

RUN_ID="${WAN22_RUN_ID:-wan22_weights_$(date -u +%Y%m%dT%H%M%SZ)_$$}"
LOG_DIR="${ROOT}/logs"
LOCK_DIR="${ROOT}/.download.lock"
MARKER="${TARGET}/.wan22_t2v_a14b.identity"
COMPLETE_MARKER="${TARGET}/.wan22_t2v_a14b.complete"
INVENTORY="${TARGET}/.wan22_t2v_a14b.inventory.json"
COMPLETE_TMP=""
IDENTITY_TMP=""
INVENTORY_TMP=""
TARGET_IDENTITY=""
LOG="${LOG_DIR}/${RUN_ID}.log"
IDENTITY="${LOG_DIR}/${RUN_ID}.identity"
EXIT_MARKER="${LOG_DIR}/${RUN_ID}.exit"
BOOT_DIR="${ROOT}/.run-markers"
BOOT_EXIT="${BOOT_DIR}/${RUN_ID}.exit"
BOOT_IDENTITY="${BOOT_DIR}/${RUN_ID}.identity"
BOOT_LOG="${BOOT_DIR}/${RUN_ID}.bootstrap.log"
LOCK_HELD=0
METHOD="not_started"
START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

[[ "${RUN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "unsafe RUN_ID: ${RUN_ID}" >&2; exit 2; }
mkdir -p "${ROOT}" "${BOOT_DIR}"
for path in "${BOOT_EXIT}" "${BOOT_IDENTITY}" "${BOOT_LOG}"; do
  [[ ! -e "${path}" ]] || { echo "bootstrap artifact already exists: ${path}" >&2; exit 2; }
done
: >"${BOOT_EXIT}" || { echo "cannot create bootstrap exit marker: ${BOOT_EXIT}" >&2; exit 2; }
: >"${BOOT_IDENTITY}" || { echo "cannot create bootstrap identity: ${BOOT_IDENTITY}" >&2; exit 2; }
: >"${BOOT_LOG}" || { echo "cannot create bootstrap log: ${BOOT_LOG}" >&2; exit 2; }
printf 'run_id=%s\nstart_utc=%s\nroot=%s\ntest_mode=%s\n' \
  "${RUN_ID}" "${START_UTC}" "${ROOT}" "${TEST_MODE}" >"${BOOT_IDENTITY}"
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

mkdir -p "${LOG_DIR}"
for path in "${LOG}" "${IDENTITY}" "${EXIT_MARKER}"; do
  [[ ! -e "${path}" ]] || { echo "run artifact already exists; refusing overwrite: ${path}" >&2; exit 2; }
done
: >"${LOG}"
: >"${IDENTITY}"
exec >>"${LOG}" 2>&1
printf 'run_id=%s\nstart_utc=%s\nsource=%s\nmodel_id=%s\nrevision=%s\n' \
  "${RUN_ID}" "${START_UTC}" "${DOWNLOAD_SOURCE}" "${MODEL_ID}" "${REVISION}" >"${IDENTITY}"
trap - ERR EXIT

on_err() {
  printf 'error_utc=%s\nerror_rc=%s\nerror_line=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >>"${LOG}"
}
release_lock() {
  local expected_lock="${ROOT}/.download.lock"
  local expected_owner="${ROOT}/.download.lock/owner"
  if [[ "${LOCK_HELD}" -eq 1 && "${LOCK_DIR}" == "${expected_lock}" \
        && "${LOCK_DIR}/owner" == "${expected_owner}" && -d "${LOCK_DIR}" ]]; then
    rm -f -- "${expected_owner}" || true
    rmdir -- "${LOCK_DIR}" || true
  fi
}
cleanup_complete_temp() {
  if [[ -n "${COMPLETE_TMP}" && -f "${COMPLETE_TMP}" && ! -L "${COMPLETE_TMP}" ]]; then
    rm -f -- "${COMPLETE_TMP}" || true
  fi
  COMPLETE_TMP=""
}
cleanup_identity_temp() {
  if [[ -n "${IDENTITY_TMP}" && -f "${IDENTITY_TMP}" && ! -L "${IDENTITY_TMP}" ]]; then
    rm -f -- "${IDENTITY_TMP}" || true
  fi
  IDENTITY_TMP=""
}
cleanup_inventory_temp() {
  if [[ -n "${INVENTORY_TMP}" && -f "${INVENTORY_TMP}" && ! -L "${INVENTORY_TMP}" ]]; then
    rm -f -- "${INVENTORY_TMP}" || true
  fi
  INVENTORY_TMP=""
}
on_exit() {
  local rc="$?"
  trap - ERR EXIT
  printf 'run_id=%s\nstart_utc=%s\nend_utc=%s\nexit_code=%s\nsource=%s\nmodel_id=%s\nrevision=%s\nmethod=%s\n' \
    "${RUN_ID}" "${START_UTC}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${rc}" \
    "${DOWNLOAD_SOURCE}" "${MODEL_ID}" "${REVISION}" "${METHOD}" >"${EXIT_MARKER}"
  printf 'run_id=%s\nstart_utc=%s\nend_utc=%s\nexit_code=%s\nsource=%s\nmodel_id=%s\nrevision=%s\nmethod=%s\n' \
    "${RUN_ID}" "${START_UTC}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${rc}" \
    "${DOWNLOAD_SOURCE}" "${MODEL_ID}" "${REVISION}" "${METHOD}" >"${BOOT_EXIT}" || true
  cleanup_complete_temp
  cleanup_identity_temp
  cleanup_inventory_temp
  release_lock
  exit "${rc}"
}
trap 'on_err "$?" "$LINENO"' ERR
trap on_exit EXIT

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "weight download lock is held: ${LOCK_DIR}"
  exit 3
fi
LOCK_HELD=1
printf 'lock_owner_run_id=%s\nlock_pid=%s\n' "${RUN_ID}" "$$" >"${LOCK_DIR}/owner"

if [[ ! -f "${REQUIRED_FILES}" || -L "${REQUIRED_FILES}" || ! -f "${AUDIT_PY}" || -L "${AUDIT_PY}" ]]; then
  echo "required inventory or audit files are missing"
  exit 2
fi
EXPECTED_MANIFEST_SHA256="$(sha256sum "${REQUIRED_FILES}" | awk '{print $1}')"
ACTUAL_AUDIT_SHA256="$(sha256sum "${AUDIT_PY}" | awk '{print $1}')"
IFS=$'\t' read -r EXPECTED_FILE_COUNT EXPECTED_TOTAL_BYTES < <(
  awk -F '\t' '!/^#/ && NF {count++; total += $2} END {print count "\t" total}' "${REQUIRED_FILES}"
)
[[ "${EXPECTED_FILE_COUNT}" =~ ^[1-9][0-9]*$ ]] || { echo "invalid required file count"; exit 2; }
[[ "${EXPECTED_TOTAL_BYTES}" =~ ^[0-9]+$ ]] || { echo "invalid required total bytes"; exit 2; }
printf 'manifest_sha256=%s\nexpected_file_count=%s\nexpected_total_bytes=%s\naudit_sha256=%s\n' \
  "${EXPECTED_MANIFEST_SHA256}" "${EXPECTED_FILE_COUNT}" "${EXPECTED_TOTAL_BYTES}" "${ACTUAL_AUDIT_SHA256}" >>"${IDENTITY}"

if [[ "${TEST_MODE}" == "0" ]]; then
  [[ "${EXPECTED_MANIFEST_SHA256}" == "${PROD_MANIFEST_SHA256}" ]] || { echo "production manifest hash mismatch"; exit 2; }
  [[ "${EXPECTED_FILE_COUNT}" == "${PROD_FILE_COUNT}" && "${EXPECTED_TOTAL_BYTES}" == "${PROD_TOTAL_BYTES}" ]] || {
    echo "production manifest count/bytes mismatch"; exit 2;
  }
  [[ "${ACTUAL_AUDIT_SHA256}" == "${PROD_AUDIT_SHA256}" ]] || { echo "production audit hash mismatch"; exit 2; }
  [[ -f "${SNAPSHOT}" && ! -L "${SNAPSHOT}" && -f "${SNAPSHOT_PY}" && ! -L "${SNAPSHOT_PY}" ]] || {
    echo "production ModelScope snapshot/verifier missing"; exit 2;
  }
  ACTUAL_SNAPSHOT_SHA256="$(sha256sum "${SNAPSHOT}" | awk '{print $1}')"
  [[ "${ACTUAL_SNAPSHOT_SHA256}" == "${PROD_SNAPSHOT_SHA256}" ]] || { echo "production snapshot hash mismatch"; exit 2; }
  ACTUAL_SNAPSHOT_PY_SHA256="$(sha256sum "${SNAPSHOT_PY}" | awk '{print $1}')"
  [[ "${ACTUAL_SNAPSHOT_PY_SHA256}" == "${PROD_SNAPSHOT_PY_SHA256}" ]] || { echo "production snapshot verifier hash mismatch"; exit 2; }
  "${SOURCE_ENV}/bin/python" "${SNAPSHOT_PY}" --snapshot "${SNAPSHOT}" --manifest "${REQUIRED_FILES}" >/dev/null
else
  ACTUAL_SNAPSHOT_SHA256=""
  ACTUAL_SNAPSHOT_PY_SHA256=""
  if [[ -n "${SNAPSHOT}" || -n "${SNAPSHOT_PY}" ]]; then
    [[ -n "${SNAPSHOT}" && -n "${SNAPSHOT_PY}" && -f "${SNAPSHOT}" && ! -L "${SNAPSHOT}" && -f "${SNAPSHOT_PY}" && ! -L "${SNAPSHOT_PY}" ]] || {
      echo "test snapshot and verifier must be supplied together"; exit 2;
    }
    "${SOURCE_ENV}/bin/python" "${SNAPSHOT_PY}" --snapshot "${SNAPSHOT}" --manifest "${REQUIRED_FILES}" >/dev/null
    ACTUAL_SNAPSHOT_SHA256="$(sha256sum "${SNAPSHOT}" | awk '{print $1}')"
    ACTUAL_SNAPSHOT_PY_SHA256="$(sha256sum "${SNAPSHOT_PY}" | awk '{print $1}')"
  fi
fi
printf 'snapshot_sha256=%s\nsnapshot_py_sha256=%s\n' "${ACTUAL_SNAPSHOT_SHA256}" "${ACTUAL_SNAPSHOT_PY_SHA256}" >>"${IDENTITY}"

marker_matches() {
  [[ -f "${MARKER}" && ! -L "${MARKER}" ]] || return 1
  grep -Fxq "source=${DOWNLOAD_SOURCE}" "${MARKER}" && \
    grep -Fxq "model_id=${MODEL_ID}" "${MARKER}" && \
    grep -Fxq "revision=${REVISION}" "${MARKER}" && \
    grep -Fxq "manifest_sha256=${EXPECTED_MANIFEST_SHA256}" "${MARKER}" && \
    grep -Fxq "required_files_sha256=${EXPECTED_MANIFEST_SHA256}" "${MARKER}" && \
    grep -Fxq "expected_file_count=${EXPECTED_FILE_COUNT}" "${MARKER}" && \
    grep -Fxq "expected_total_bytes=${EXPECTED_TOTAL_BYTES}" "${MARKER}" && \
  grep -Fxq "audit_sha256=${ACTUAL_AUDIT_SHA256}" "${MARKER}"
}
capture_target_identity() {
  [[ -d "${TARGET}" && ! -L "${TARGET}" ]] || {
    echo "target is not a regular directory while capturing identity" >&2
    return 1
  }
  TARGET_IDENTITY="$(stat -c '%d:%i' -- "${TARGET}")"
  [[ -n "${TARGET_IDENTITY}" ]] || {
    echo "could not capture target directory identity" >&2
    return 1
  }
}
assert_target_identity() {
  local current
  [[ -n "${TARGET_IDENTITY}" ]] || return 1
  [[ -d "${TARGET}" && ! -L "${TARGET}" ]] || {
    echo "target directory was replaced or symlinked during operation" >&2
    return 1
  }
  current="$(stat -c '%d:%i' -- "${TARGET}")"
  [[ "${current}" == "${TARGET_IDENTITY}" ]] || {
    echo "target directory identity changed: expected=${TARGET_IDENTITY} actual=${current}" >&2
    return 1
  }
}
write_identity_marker() {
  assert_target_identity || return 1
  if [[ -e "${MARKER}" || -L "${MARKER}" ]]; then
    marker_matches || { echo "existing identity marker is missing or mismatched"; return 1; }
    return 0
  fi
  IDENTITY_TMP="$(mktemp --tmpdir="${ROOT}" ".wan22_t2v_a14b.identity.tmp-${RUN_ID}.XXXXXX")"
  [[ -f "${IDENTITY_TMP}" && ! -L "${IDENTITY_TMP}" ]] || {
    echo "identity marker temporary file is not a regular file"; return 1;
  }
  printf 'source=%s\nmodel_id=%s\nrevision=%s\nmanifest_sha256=%s\nrequired_files_sha256=%s\nexpected_file_count=%s\nexpected_total_bytes=%s\naudit_sha256=%s\ncreated_utc=%s\n' \
    "${DOWNLOAD_SOURCE}" "${MODEL_ID}" "${REVISION}" "${EXPECTED_MANIFEST_SHA256}" \
    "${EXPECTED_MANIFEST_SHA256}" "${EXPECTED_FILE_COUNT}" "${EXPECTED_TOTAL_BYTES}" \
    "${ACTUAL_AUDIT_SHA256}" "${START_UTC}" >"${IDENTITY_TMP}"
  [[ -f "${IDENTITY_TMP}" && ! -L "${IDENTITY_TMP}" ]] || {
    echo "identity marker temporary file was replaced"; return 1;
  }
  assert_target_identity || return 1
  if ! mv -T --no-clobber -- "${IDENTITY_TMP}" "${MARKER}"; then
    echo "atomic identity marker publish failed"
    return 1
  fi
  IDENTITY_TMP=""
  assert_target_identity || return 1
  marker_matches || { echo "identity marker postcheck failed"; return 1; }
}
audit_complete() {
  if [[ -e "${INVENTORY}" || -L "${INVENTORY}" ]]; then
    [[ -f "${INVENTORY}" && ! -L "${INVENTORY}" ]] || return 1
  fi
  assert_target_identity || return 1
  INVENTORY_TMP="$(mktemp --tmpdir="${ROOT}" ".wan22_t2v_a14b.inventory.tmp-${RUN_ID}.XXXXXX")"
  [[ -f "${INVENTORY_TMP}" && ! -L "${INVENTORY_TMP}" ]] || {
    echo "inventory temporary file is not a regular file"; return 1;
  }
  "${SOURCE_ENV}/bin/python" "${AUDIT_PY}" --root "${TARGET}" \
    --required-files "${REQUIRED_FILES}" --output "${INVENTORY_TMP}" >/dev/null
  [[ -f "${INVENTORY_TMP}" && ! -L "${INVENTORY_TMP}" && -s "${INVENTORY_TMP}" ]] || return 1
  assert_target_identity || return 1
  if [[ -e "${INVENTORY}" || -L "${INVENTORY}" ]]; then
    [[ -f "${INVENTORY}" && ! -L "${INVENTORY}" ]] || return 1
    cmp -s -- "${INVENTORY_TMP}" "${INVENTORY}" || {
      echo "existing inventory is missing or mismatched" >&2
      return 1
    }
    cleanup_inventory_temp
  else
    if ! mv -T --no-clobber -- "${INVENTORY_TMP}" "${INVENTORY}"; then
      echo "atomic inventory publish failed" >&2
      return 1
    fi
    INVENTORY_TMP=""
  fi
  assert_target_identity || return 1
  [[ -f "${INVENTORY}" && ! -L "${INVENTORY}" && -s "${INVENTORY}" ]]
}
inventory_sha256() { sha256sum "${INVENTORY}" | awk '{print $1}'; }
complete_marker_matches() {
  [[ -f "${COMPLETE_MARKER}" && ! -L "${COMPLETE_MARKER}" ]] || return 1
  [[ -f "${INVENTORY}" && ! -L "${INVENTORY}" ]] || return 1
  local inventory_hash
  inventory_hash="$(inventory_sha256)"
  grep -Fxq "source=${DOWNLOAD_SOURCE}" "${COMPLETE_MARKER}" && \
    grep -Fxq "model_id=${MODEL_ID}" "${COMPLETE_MARKER}" && \
    grep -Fxq "revision=${REVISION}" "${COMPLETE_MARKER}" && \
    grep -Fxq "manifest_sha256=${EXPECTED_MANIFEST_SHA256}" "${COMPLETE_MARKER}" && \
    grep -Fxq "required_files_sha256=${EXPECTED_MANIFEST_SHA256}" "${COMPLETE_MARKER}" && \
    grep -Fxq "expected_file_count=${EXPECTED_FILE_COUNT}" "${COMPLETE_MARKER}" && \
    grep -Fxq "expected_total_bytes=${EXPECTED_TOTAL_BYTES}" "${COMPLETE_MARKER}" && \
    grep -Fxq "audit_sha256=${ACTUAL_AUDIT_SHA256}" "${COMPLETE_MARKER}" && \
    grep -Fxq "inventory_sha256=${inventory_hash}" "${COMPLETE_MARKER}"
}
write_complete_marker() {
  assert_target_identity || return 1
  local inventory_hash
  inventory_hash="$(inventory_sha256)"
  if [[ -e "${COMPLETE_MARKER}" || -L "${COMPLETE_MARKER}" ]]; then
    complete_marker_matches || { echo "existing complete marker is missing or mismatched"; return 1; }
    return 0
  fi
  COMPLETE_TMP="$(mktemp --tmpdir="${TARGET}" ".wan22_t2v_a14b.complete.tmp-${RUN_ID}.XXXXXX")"
  [[ -f "${COMPLETE_TMP}" && ! -L "${COMPLETE_TMP}" ]] || {
    echo "complete marker temporary file is not a regular file"; return 1;
  }
  printf 'source=%s\nmodel_id=%s\nrevision=%s\nmanifest_sha256=%s\nrequired_files_sha256=%s\nexpected_file_count=%s\nexpected_total_bytes=%s\naudit_sha256=%s\ninventory_sha256=%s\ncompleted_utc=%s\n' \
    "${DOWNLOAD_SOURCE}" "${MODEL_ID}" "${REVISION}" "${EXPECTED_MANIFEST_SHA256}" \
    "${EXPECTED_MANIFEST_SHA256}" "${EXPECTED_FILE_COUNT}" "${EXPECTED_TOTAL_BYTES}" \
    "${ACTUAL_AUDIT_SHA256}" "${inventory_hash}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"${COMPLETE_TMP}"
  [[ -f "${COMPLETE_TMP}" && ! -L "${COMPLETE_TMP}" ]] || {
    echo "complete marker temporary file was replaced"; return 1;
  }
  if ! mv -T --no-clobber -- "${COMPLETE_TMP}" "${COMPLETE_MARKER}"; then
    echo "atomic complete marker publish failed"; return 1
  fi
  COMPLETE_TMP=""
  assert_target_identity || return 1
  complete_marker_matches || { echo "complete marker postcheck failed"; return 1; }
}

publish_link() {
  assert_target_identity || return 1
  if [[ -e "${LINK}" || -L "${LINK}" ]]; then
    [[ -L "${LINK}" ]] || { echo "public link is not a symlink"; return 1; }
    [[ "$(readlink "${LINK}")" == "${CONTAINER_TARGET}" ]] || { echo "public link target mismatch"; return 1; }
    audit_complete && complete_marker_matches || { echo "matching link lacks exact complete artifact"; return 1; }
    echo "existing matching complete public link accepted"
    return 0
  fi
  if ln -sT "${CONTAINER_TARGET}" "${LINK}"; then
    [[ -L "${LINK}" && "$(readlink "${LINK}")" == "${CONTAINER_TARGET}" ]] || {
      echo "public link postcheck failed"; return 1;
    }
    echo "published_public_link=$(readlink "${LINK}")"
    return 0
  else
    local rc=$?
    if [[ -L "${LINK}" && "$(readlink "${LINK}")" == "${CONTAINER_TARGET}" ]] && \
       audit_complete && complete_marker_matches; then
      echo "matching complete public link accepted after publish race"
      return 0
    fi
    echo "public link creation failed rc=${rc}"
    return "${rc}"
  fi
}

if [[ -e "${LINK}" || -L "${LINK}" ]]; then
  [[ -L "${LINK}" && "$(readlink "${LINK}")" == "${CONTAINER_TARGET}" ]] || {
    echo "pre-existing public link is not the exact expected symlink"; exit 2;
  }
  marker_matches || { echo "pre-existing public link marker mismatch"; exit 2; }
  capture_target_identity
  audit_complete || { echo "pre-existing public link target audit failed"; exit 2; }
  complete_marker_matches || { echo "pre-existing public link complete marker mismatch"; exit 2; }
  publish_link
  exit 0
fi

if [[ -e "${TARGET}" || -L "${TARGET}" ]]; then
  [[ -d "${TARGET}" && ! -L "${TARGET}" ]] || { echo "target is not a regular directory"; exit 2; }
  marker_matches || { echo "existing target marker mismatch; refusing resume"; exit 2; }
else
  mkdir -p "${TARGET}"
fi
capture_target_identity
write_identity_marker

run_modelscope() {
  local bin="${MODELSCOPE_BIN}"
  [[ -n "${bin}" && -x "${bin}" ]] || return 127
  METHOD="modelscope"
  MODELSCOPE_SELECTED_BIN="${bin}"
  printf 'modelscope_bin=%s\n' "${bin}" >>"${IDENTITY}"
  echo "modelscope_bin=${bin}"
  if "${bin}" --version >/dev/null 2>&1; then
    echo "modelscope_version_probe=ok"
  else
    echo "modelscope_version_probe=unsupported_or_failed"
  fi
  "${bin}" download --model "${MODEL_ID}" --revision "${REVISION}" --local_dir "${TARGET}"
}
run_python_modelscope() {
  [[ -x "${SOURCE_ENV}/bin/python" ]] || return 127
  "${SOURCE_ENV}/bin/python" -c 'import modelscope' >/dev/null 2>&1 || return 127
  METHOD="python-modelscope"
  "${SOURCE_ENV}/bin/python" -m modelscope download --model "${MODEL_ID}" --revision "${REVISION}" --local_dir "${TARGET}"
}
run_huggingface_cli() {
  command -v huggingface-cli >/dev/null 2>&1 || return 127
  METHOD="huggingface-cli"
  huggingface-cli download "${MODEL_ID}" --repo-type model --revision "${REVISION}" --local-dir "${TARGET}" --resume-download
}
run_python_huggingface() {
  [[ -x "${SOURCE_ENV}/bin/python" ]] || return 127
  "${SOURCE_ENV}/bin/python" -c 'import huggingface_hub' >/dev/null 2>&1 || return 127
  METHOD="python-huggingface_hub"
  "${SOURCE_ENV}/bin/python" -m huggingface_hub.commands.huggingface_cli download "${MODEL_ID}" --repo-type model --revision "${REVISION}" --local-dir "${TARGET}" --resume-download
}

case "${DOWNLOAD_SOURCE}" in
  modelscope)
    [[ "${REVISION}" == "master" ]] || { echo "ModelScope source requires revision=master"; exit 2; }
    if run_modelscope; then
      :
    else
      rc=$?
      if run_python_modelscope; then
        :
      else
        rc=$?
        echo "all ModelScope download methods failed; final_rc=${rc}"
        exit "${rc}"
      fi
    fi
    ;;
  hf)
    [[ "${TEST_MODE}" == "1" && "${REVISION}" == "main" ]] || { echo "HF is test-only and requires revision=main"; exit 2; }
    if run_huggingface_cli; then
      :
    else
      rc=$?
      if run_python_huggingface; then
        :
      else
        rc=$?
        echo "all HF download methods failed; final_rc=${rc}"
        exit "${rc}"
      fi
    fi
    ;;
  *) echo "unsupported download source: ${DOWNLOAD_SOURCE}"; exit 2 ;;
esac

audit_complete
assert_target_identity
write_complete_marker
complete_marker_matches || { echo "complete marker postcheck failed"; exit 1; }
assert_target_identity
publish_link
exit 0
