#!/bin/bash
set -e
# Schema-isolated databases per service — SRV-HTZNR-EU-SWS
# Runs once on first postgres container init.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE autoagent;
    CREATE DATABASE cua;
    CREATE DATABASE trend_radar;
    CREATE DATABASE synapse;

    CREATE ROLE autoagent_user  WITH LOGIN PASSWORD '${AUTOAGENT_DB_PASSWORD:-changeme_autoagent}';
    CREATE ROLE cua_user        WITH LOGIN PASSWORD '${CUA_DB_PASSWORD:-changeme_cua}';
    CREATE ROLE trend_radar_user WITH LOGIN PASSWORD '${TREND_RADAR_DB_PASSWORD:-changeme_radar}';
    CREATE ROLE synapse_user    WITH LOGIN PASSWORD '${SYNAPSE_DB_PASSWORD:-changeme_synapse}';

    GRANT ALL PRIVILEGES ON DATABASE autoagent   TO autoagent_user;
    GRANT ALL PRIVILEGES ON DATABASE cua         TO cua_user;
    GRANT ALL PRIVILEGES ON DATABASE trend_radar TO trend_radar_user;
    GRANT ALL PRIVILEGES ON DATABASE synapse     TO synapse_user;
EOSQL

# Synapse requires a specific LC_COLLATE for its schema
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname synapse <<-EOSQL
    ALTER DATABASE synapse TEMPLATE template0
        LC_COLLATE 'C' LC_CTYPE 'C';
EOSQL

echo "[init.sh] Databases and roles created."
