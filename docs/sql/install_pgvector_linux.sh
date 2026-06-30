#!/usr/bin/env bash
set -euo pipefail

# Install pgvector for a Linux PostgreSQL server.
#
# Usage:
#   chmod +x docs/sql/install_pgvector_linux.sh
#   PG_MAJOR=16 docs/sql/install_pgvector_linux.sh
#   PG_MAJOR=16 docs/sql/install_pgvector_linux.sh your_database_name
#
# Notes:
# - Packages are tried first:
#   - Debian/Ubuntu: postgresql-<major>-pgvector
#   - RHEL/Rocky/CentOS/Fedora: pgvector_<major>
# - If a package is unavailable, the script builds from source with the
#   matching PostgreSQL server development package.

PG_MAJOR="${PG_MAJOR:-16}"
DB_NAME="${1:-}"

log() {
    printf '\n==> %s\n' "$*"
}

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf 'Missing required command: %s\n' "$1" >&2
        exit 1
    fi
}

find_pg_config() {
    if command -v pg_config >/dev/null 2>&1; then
        command -v pg_config
        return
    fi

    if [ -x "/usr/lib/postgresql/${PG_MAJOR}/bin/pg_config" ]; then
        printf '/usr/lib/postgresql/%s/bin/pg_config\n' "$PG_MAJOR"
        return
    fi

    if [ -x "/usr/pgsql-${PG_MAJOR}/bin/pg_config" ]; then
        printf '/usr/pgsql-%s/bin/pg_config\n' "$PG_MAJOR"
        return
    fi

    printf 'Could not find pg_config for PostgreSQL %s\n' "$PG_MAJOR" >&2
    exit 1
}

vector_control_exists() {
    local pg_config_bin="$1"
    local sharedir
    sharedir="$("$pg_config_bin" --sharedir)"
    test -f "${sharedir}/extension/vector.control"
}

install_from_apt() {
    local pkg="postgresql-${PG_MAJOR}-pgvector"

    log "Trying apt package: ${pkg}"
    sudo apt-get update

    if apt-cache show "$pkg" >/dev/null 2>&1; then
        sudo apt-get install -y "$pkg"
        return 0
    fi

    log "Package ${pkg} not found in configured apt repositories"
    return 1
}

install_from_yum_or_dnf() {
    local pm="$1"
    local pkg="pgvector_${PG_MAJOR}"

    log "Trying ${pm} package: ${pkg}"
    if sudo "$pm" install -y "$pkg"; then
        return 0
    fi

    log "Package ${pkg} not found in configured yum/dnf repositories"
    return 1
}

install_build_deps_apt() {
    sudo apt-get update
    sudo apt-get install -y \
        build-essential \
        ca-certificates \
        git \
        "postgresql-server-dev-${PG_MAJOR}"
}

install_build_deps_yum_or_dnf() {
    local pm="$1"

    sudo "$pm" install -y git make gcc

    if ! sudo "$pm" install -y "postgresql${PG_MAJOR}-devel"; then
        sudo "$pm" install -y postgresql-server-devel
    fi
}

build_from_source() {
    local pg_config_bin="$1"
    local tmpdir

    need_cmd git
    need_cmd make

    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT

    log "Building pgvector from source with ${pg_config_bin}"
    git clone --depth 1 https://github.com/pgvector/pgvector.git "$tmpdir/pgvector"
    make -C "$tmpdir/pgvector" PG_CONFIG="$pg_config_bin"
    sudo make -C "$tmpdir/pgvector" PG_CONFIG="$pg_config_bin" install
}

enable_extension() {
    local db_name="$1"

    if [ -z "$db_name" ]; then
        log "Skipping CREATE EXTENSION because no database name was passed"
        printf 'Run this after connecting to the target database:\n'
        printf '  CREATE EXTENSION IF NOT EXISTS vector;\n'
        return
    fi

    log "Enabling vector extension in database: ${db_name}"
    sudo -u postgres psql -d "$db_name" -c "CREATE EXTENSION IF NOT EXISTS vector;"
    sudo -u postgres psql -d "$db_name" -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
}

main() {
    local pg_config_bin

    log "Installing pgvector for PostgreSQL ${PG_MAJOR}"

    if command -v apt-get >/dev/null 2>&1; then
        if ! install_from_apt; then
            install_build_deps_apt
            pg_config_bin="$(find_pg_config)"
            build_from_source "$pg_config_bin"
        fi
    elif command -v dnf >/dev/null 2>&1; then
        if ! install_from_yum_or_dnf dnf; then
            install_build_deps_yum_or_dnf dnf
            pg_config_bin="$(find_pg_config)"
            build_from_source "$pg_config_bin"
        fi
    elif command -v yum >/dev/null 2>&1; then
        if ! install_from_yum_or_dnf yum; then
            install_build_deps_yum_or_dnf yum
            pg_config_bin="$(find_pg_config)"
            build_from_source "$pg_config_bin"
        fi
    else
        printf 'Unsupported Linux package manager. Install pgvector manually or add support to this script.\n' >&2
        exit 1
    fi

    pg_config_bin="$(find_pg_config)"
    if vector_control_exists "$pg_config_bin"; then
        log "vector.control installed under $("$pg_config_bin" --sharedir)/extension"
    else
        printf 'pgvector install finished, but vector.control was not found for this PostgreSQL install.\n' >&2
        printf 'Check that PG_MAJOR=%s matches the running PostgreSQL server.\n' "$PG_MAJOR" >&2
        exit 1
    fi

    enable_extension "$DB_NAME"

    log "Done"
}

main "$@"
