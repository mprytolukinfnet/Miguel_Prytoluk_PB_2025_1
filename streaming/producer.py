import os
import time
import logging
import pandas as pd
import boto3
from botocore.exceptions import ClientError
from kafka import KafkaProducer
import json
import io

# Configura o sistema de logging para exibir informações claras sobre o processo.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configurações ---
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'kafka:29092')
KAFKA_TOPIC = 'taxi_trips'
INPUT_BUCKET = os.getenv('SILVER_BUCKET', 'silver-bucket')
INPUT_FILE_KEY = "processed/yellow_tripdata_2023-01.parquet"


def get_s3_client():
    """Cria e retorna um cliente S3 configurado para o MinIO."""
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )

def wait_for_s3_file(s3_client, bucket, key, retries=30, delay=30):
    """Espera ativamente até que um arquivo exista no S3/MinIO."""
    logging.info(f"Aguardando pelo arquivo de entrada em: s3://{bucket}/{key}")
    for i in range(retries):
        try:
            s3_client.head_object(Bucket=bucket, Key=key)
            logging.info("Arquivo de entrada encontrado! Iniciando o processo.")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logging.info(f"Arquivo ainda não encontrado. Tentativa {i + 1}/{retries}. Nova verificação em {delay}s...")
                time.sleep(delay)
            else:
                logging.error(f"Erro inesperado ao acessar o MinIO: {e}")
                raise
    logging.error("Tempo de espera excedido. O arquivo de entrada do pipeline de batch não foi encontrado.")
    return False

def create_kafka_producer():
    """Cria e retorna um produtor Kafka, com retentativas de conexão."""
    logging.info(f"Tentando se conectar ao Kafka em {KAFKA_BROKER}...")
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            logging.info("Produtor Kafka conectado com sucesso.")
            return producer
        except Exception as e:
            logging.error(f"Não foi possível conectar ao Kafka. Tentando novamente em 15s... Erro: {e}")
            time.sleep(15)

def run_producer():
    """Função principal que orquestra a espera, leitura e produção das mensagens."""
    s3_client = get_s3_client()

    if not wait_for_s3_file(s3_client, INPUT_BUCKET, INPUT_FILE_KEY):
        logging.info("Encerrando o produtor pois o arquivo de entrada não foi gerado a tempo.")
        return

    producer = create_kafka_producer()

    try:
        # Pega o objeto do MinIO
        obj = s3_client.get_object(Bucket=INPUT_BUCKET, Key=INPUT_FILE_KEY)
        
        # Lê o conteúdo do streaming para um buffer em memória (BytesIO)
        parquet_file_buffer = io.BytesIO(obj['Body'].read())
        
        df = pd.read_parquet(parquet_file_buffer)
        
        df_sample = df.sample(n=1000, random_state=42)
        logging.info(f"Arquivo Parquet lido da camada Silver. {len(df_sample)} registros de amostra serão enviados.")

    except Exception as e:
        logging.error(f"Falha ao ler o arquivo Parquet do MinIO: {e}")
        return

    for index, row in df_sample.iterrows():
        message = row.to_dict()
        for key, value in message.items():
            if isinstance(value, pd.Timestamp):
                message[key] = value.isoformat()
        
        producer.send(KAFKA_TOPIC, value=message)
        
        vendor_id = message.get('VendorID')
        fare = message.get('fare_amount')
        logging.info(f"--> Mensagem enviada: VendorID={vendor_id}, Tarifa={fare}")

        time.sleep(0.1)

    producer.flush()
    logging.info("Produção de mensagens concluída com sucesso.")


if __name__ == "__main__":
    run_producer()