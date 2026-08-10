#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
install_directory="${INSTALL_BIN_DIR:-${HOME}/.local/bin}"
executables=()
command_names=()

shopt -s nullglob
for executable in "${repository_root}"/tools/*/bin/* "${repository_root}"/apps/*/bin/*; do
  if [[ ! -f "${executable}" || ! -x "${executable}" ]]; then
    continue
  fi

  command_name="$(basename "${executable}")"
  for existing_name in "${command_names[@]+"${command_names[@]}"}"; do
    if [[ "${existing_name}" == "${command_name}" ]]; then
      printf 'error: multiple projects provide the command %s\n' "${command_name}" >&2
      exit 1
    fi
  done

  destination="${install_directory}/${command_name}"
  if [[ -e "${destination}" && ! -L "${destination}" ]]; then
    printf 'error: refusing to replace existing non-symlink %s\n' "${destination}" >&2
    exit 1
  fi

  executables+=("${executable}")
  command_names+=("${command_name}")
done

mkdir -p "${install_directory}"

for executable in "${executables[@]+"${executables[@]}"}"; do
  destination="${install_directory}/$(basename "${executable}")"
  ln -sfn "${executable}" "${destination}"
  printf 'linked %s -> %s\n' "${destination}" "${executable}"
done

printf 'Installed %s commands into %s\n' "${#executables[@]}" "${install_directory}"
