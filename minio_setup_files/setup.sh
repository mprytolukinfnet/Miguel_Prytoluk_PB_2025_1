#!/bin/sh

set -e

echo "Aguardando o MinIO ficar online..."
mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} --api s3v4
echo "MinIO está online."

mc admin policy remove local analyst-policy || true
mc admin policy remove local ingestion-policy || true

echo "Criando/Atualizando políticas..."
mc admin policy create local analyst-policy /setup/analyst_policy.json
mc admin policy create local ingestion-policy /setup/ingestion_policy.json
echo "Políticas criadas/atualizadas."

echo "Criando/Verificando usuários..."
mc admin user add local ana.stark password123 || echo "Usuário 'ana.stark' já existe."
mc admin user add local ingestion_bot s3rv1c3p4ss || echo "Usuário 'ingestion_bot' já existe."

echo "Anexando políticas..."
mc admin policy attach local analyst-policy --user ana.stark
mc admin policy attach local ingestion-policy --user ingestion_bot
echo "Políticas anexadas."

echo "🎉 Setup do MinIO concluído com sucesso!"
exit 0