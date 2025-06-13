#!/bin/bash

# Aguarda o Airflow webserver estar pronto
echo "Aguardando o Airflow webserver estar pronto..."
while ! nc -z airflow-webserver 8080; do   
  sleep 5
done

echo "Airflow webserver está pronto. Aguardando mais 10 segundos para garantir..."
sleep 10

echo "Disparando o DAG..."
airflow dags trigger batch_pipeline_taxi_nyc_enhanced

echo "DAG disparado com sucesso!"
