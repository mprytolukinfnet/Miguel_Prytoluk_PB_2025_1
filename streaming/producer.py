# Este script simula o fluxo de dados em tempo real.
# Ele lê os dados do nosso Data Lake (camada Bronze no MinIO) e envia para o Kafka.
import pandas as pd
from kafka import KafkaProducer
import json
import time
import os
from pathlib import Path
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações para ler do MinIO
MINIO_ENDPOINT = 'http://minio:9000'
MINIO_ACCESS_KEY = os.getenv('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
BRONZE_BUCKET = os.getenv('BRONZE_BUCKET')
TRIP_DATA_FILE_NAME = "yellow_tripdata_2023-01.parquet"

def read_parquet_with_retry(max_attempts=30, delay_seconds=10):
    """Tenta ler o arquivo parquet com retries"""
    storage_options = {
        "client_kwargs": {
            "endpoint_url": MINIO_ENDPOINT,
            "aws_access_key_id": MINIO_ACCESS_KEY,
            "aws_secret_access_key": MINIO_SECRET_KEY
        }
    }
    
    attempt = 0
    while attempt < max_attempts:
        try:
            logger.info(f"Tentativa {attempt + 1} de {max_attempts} para ler os dados do MinIO...")
            df = pd.read_parquet(
                f"s3://{BRONZE_BUCKET}/raw/{TRIP_DATA_FILE_NAME}",
                storage_options=storage_options
            )
            logger.info("Dados lidos com sucesso!")
            return df.sample(n=500, random_state=42)
        except Exception as e:
            attempt += 1
            if attempt < max_attempts:
                logger.warning(f"Tentativa {attempt} falhou. Erro: {str(e)}")
                logger.info(f"Aguardando {delay_seconds} segundos antes da próxima tentativa...")
                time.sleep(delay_seconds)
            else:
                logger.error("Número máximo de tentativas atingido. Encerrando...")
                raise

print("Lendo dados do MinIO para simular o stream...")
df_sample = read_parquet_with_retry()

producer = KafkaProducer(
    bootstrap_servers='kafka:29092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)
KAFKA_TOPIC = 'taxi_trips'

print(f"Iniciando o envio de {len(df_sample)} mensagens para o tópico '{KAFKA_TOPIC}'...")
for _, row in df_sample.iterrows():
    message = {k: str(v) for k, v in row.to_dict().items()}
    producer.send(KAFKA_TOPIC, message)
    print(f"--> Mensagem enviada: VendorID {message.get('VendorID')}, Tarifa {message.get('fare_amount')}")
    time.sleep(0.2) # Pausa para simular o fluxo

producer.flush()
print("Envio de mensagens concluído.")