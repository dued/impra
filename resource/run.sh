#!/bin/bash

RESULT_OK=0
RESULT_NOK=1
RESULT_FAIL=2

DB_NAME="impra"
VOLUME_DIR="/var/lib/odoo"
VERSION_FILE="$VOLUME_DIR/last_version.txt"
CURRENT_VERSION=$(odoo --version)

function abort {
  reason=$1
  echo "Fatal: $reason"
  exit 1
}

function check_db {
  echo "Espere hasta que la base de datos se esté ejecutando..."
  if ! wait-for-psql.py --db_host "$HOST" --db_port 5432 --db_user "$USER" --db_password "$PASSWORD" --timeout 60; then
    return $RESULT_FAIL
  fi

  echo "Compruebe si existe la tabla 'res_users'..."
  PGHOST="$HOST" PGUSER="$USER" PGPASSWORD="$PASSWORD" PGDATABASE="$DB_NAME" \
    psql -qc "select * from res_users" \
    >/dev/null

  RESULT_CODE=$?
  echo "PSQL exit code: $RESULT_CODE"

  return $RESULT_CODE
}

function init_db {
  /entrypoint.sh "$@" "--init" "base" "-d" "$DB_NAME" "--stop-after-init"
}

function update_db {
  /entrypoint.sh "$@" "--update" "all" "-d" "$DB_NAME" "--stop-after-init"
}

function invalidate_assets {
  if [ -f "$VERSION_FILE" ]; then
    LAST_VERSION="$(<"$VERSION_FILE")"
    echo "La última versión fue $LAST_VERSION"
  else
    LAST_VERSION="n.a."
    echo "El archivo de versión no existe"
  fi

  if [ "$CURRENT_VERSION" != "$LAST_VERSION" ]; then
    echo "La versión actual difiere de la versión anterior ($CURRENT_VERSION =/= $LAST_VERSION)"
    PGHOST="$HOST" PGUSER="$USER" PGPASSWORD="$PASSWORD" PGDATABASE="$DB_NAME" \
      psql -qc "delete from ir_attachment where res_model='ir.ui.view' and name like '%assets_%'" \
      >/dev/null
  fi
}

function print_version_file() {
  printf "%s" "$CURRENT_VERSION" >"$VERSION_FILE"
}

check_db

case $? in
"$RESULT_OK")
  echo "Base de datos ya inicializada"
  invalidate_assets
  update_db "$@"
  ;;
"$RESULT_NOK")
  echo "Inicializando base de datos"
  init_db "$@"
  ;;
*)
  abort "Error al conectar con el servidor de la base de datos"
  ;;
esac

print_version_file

exec "/entrypoint.sh" "$@"
