#!/bin/bash
set -e
# Schema-isolated databases per service — SRV-HTZNR-EU-SWS
# Runs once on first postgres container init.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE autoagent;
    CREATE DATABASE cua;
    CREATE DATABASE trend_radar;
    -- Synapse REQUIRES LC_COLLATE='C' and LC_CTYPE='C'; this must be set
    -- at CREATE time (ALTER DATABASE cannot change collation).
    CREATE DATABASE synapse
      ENCODING=UTF8
      LC_COLLATE='C'
      LC_CTYPE='C'
      TEMPLATE=template0;

    CREATE ROLE autoagent_user   WITH LOGIN PASSWORD '${AUTOAGENT_DB_PASSWORD:-changeme_autoagent}';
    CREATE ROLE cua_user         WITH LOGIN PASSWORD '${CUA_DB_PASSWORD:-changeme_cua}';
    CREATE ROLE trend_radar_user WITH LOGIN PASSWORD '${TREND_RADAR_DB_PASSWORD:-changeme_radar}';
    CREATE ROLE synapse_user     WITH LOGIN PASSWORD '${SYNAPSE_DB_PASSWORD:-changeme_synapse}';

    GRANT ALL PRIVILEGES ON DATABASE autoagent   TO autoagent_user;
    GRANT ALL PRIVILEGES ON DATABASE cua         TO cua_user;
    GRANT ALL PRIVILEGES ON DATABASE trend_radar TO trend_radar_user;
    GRANT ALL PRIVILEGES ON DATABASE synapse     TO synapse_user;
EOSQL

echo "[init.sh] Databases and roles created."

# PostgreSQL 15+ separates schema privileges from database privileges.
# GRANT ON DATABASE only allows connecting; CREATE TABLE also needs
# schema-level access. Run each grant inside the target database.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname autoagent <<-EOSQL
    GRANT ALL ON SCHEMA public TO autoagent_user;
    ALTER SCHEMA public OWNER TO autoagent_user;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname trend_radar <<-EOSQL
    GRANT ALL ON SCHEMA public TO trend_radar_user;
    ALTER SCHEMA public OWNER TO trend_radar_user;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname synapse <<-EOSQL
    GRANT ALL ON SCHEMA public TO synapse_user;
    ALTER SCHEMA public OWNER TO synapse_user;
EOSQL

echo "[init.sh] Schema grants applied. Init complete."
