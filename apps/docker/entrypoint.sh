#!/usr/bin/env bash
set -euo pipefail

CONF_DIR="${CONF_DIR:-/azerothcore/env/dist/etc}"
LOGS_DIR="${LOGS_DIR:-/azerothcore/env/dist/logs}"

if ! touch "$CONF_DIR/.write-test" || ! touch "$LOGS_DIR/.write-test"; then
    cat <<EOF
===== WARNING =====
The current user doesn't have write permissions for
the configuration dir ($CONF_DIR) or logs dir ($LOGS_DIR).
It's likely that services will fail due to this.

This is usually caused by cloning the repository as root,
so the files are owned by root (uid 0).

To resolve this, you can set the ownership of the
configuration directory with the command on the host machine.
Note that if the files are owned as root, the ownership must
be changed as root (hence sudo).

$ sudo chown -R $(id -u):$(id -g) /path/to$CONF_DIR /path/to$LOGS_DIR

Alternatively, you can set the DOCKER_USER environment
variable (on the host machine) to "root", though this
isn't recommended.

$ DOCKER_USER=root docker-compose up -d
====================
EOF
fi

[[ -f "$CONF_DIR/.write-test" ]] && rm -f "$CONF_DIR/.write-test"
[[ -f "$LOGS_DIR/.write-test" ]] && rm -f "$LOGS_DIR/.write-test"

# Copy all default config files to env/dist/etc if they don't already exist
# -r == recursive
# -n == no clobber (don't overwrite)
# -v == be verbose
cp -rnv /azerothcore/env/ref/etc/* "$CONF_DIR"

# Determine the component from the command passed to the script. Default to ACORE_COMPONENT if no args.
DETECTED_COMPONENT="$ACORE_COMPONENT"
if [[ $# -gt 0 ]] && [[ -n "$1" ]]; then
    DETECTED_COMPONENT=$(basename "$1")
fi
echo "Component determined as: $DETECTED_COMPONENT"

CONF="$CONF_DIR/$DETECTED_COMPONENT.conf"
CONF_DIST="$CONF_DIR/$DETECTED_COMPONENT.conf.dist"

# Copy the "dist" file to the "conf" if the conf doesn't already exist
if [[ -f "$CONF_DIST" ]]; then
    echo "Creating config file '$CONF' from template '$CONF_DIST'."
    cp -v "$CONF_DIST" "$CONF"
else
    echo "Warning: Config template '$CONF_DIST' not found. Creating empty config file."
    touch "$CONF"
fi

echo "Starting $DETECTED_COMPONENT..."

# For Fly.io, run dbimport before starting the server process
# to ensure the database is up-to-date.
if [[ "$DETECTED_COMPONENT" == "authserver" ]] || [[ "$DETECTED_COMPONENT" == "worldserver" ]]; then
    echo "Running dbimport before starting the server..."
    # Ensure dbimport.conf exists before running dbimport
    if [[ ! -f "$CONF_DIR/dbimport.conf" ]]; then
        echo "Creating dbimport.conf from template."
        cp -v "$CONF_DIR/dbimport.conf.dist" "$CONF_DIR/dbimport.conf"
    fi

    # Replace the default 127.0.0.1 with the Fly.io internal address for the database.
    # This MUST run after all .conf files have been created.
    echo "Updating all configuration files for Fly.io database..."
    sed -i 's/LoginDatabaseInfo = .*/LoginDatabaseInfo = "${AC_LOGIN_DATABASE_INFO}"/g' $CONF_DIR/*.conf
    sed -i 's/WorldDatabaseInfo = .*/WorldDatabaseInfo = "${AC_WORLD_DATABASE_INFO}"/g' $CONF_DIR/*.conf
    sed -i 's/CharacterDatabaseInfo = .*/CharacterDatabaseInfo = "${AC_CHARACTER_DATABASE_INFO}"/g' $CONF_DIR/*.conf

    /azerothcore/env/dist/bin/dbimport || { echo "dbimport failed!"; exit 1; }
    echo "dbimport finished."
fi

exec "$@"
