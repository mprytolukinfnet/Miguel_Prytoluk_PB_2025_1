import os
from datetime import datetime
import pandas as pd
import logging
import requests
import boto3
from botocore.client import Config
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

# --- Configurações ---
MINIO_ENDPOINT = 'http://minio:9000'
MINIO_ACCESS_KEY = os.getenv('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')

BRONZE_BUCKET = os.getenv('BRONZE_BUCKET')
SILVER_BUCKET = os.getenv('SILVER_BUCKET')
GOLD_BUCKET = os.getenv('GOLD_BUCKET')

# Fontes de dados
TRIP_DATA_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2023-01.parquet"
ZONES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi+_zone_lookup.csv"
TRIP_DATA_FILE_NAME = "yellow_tripdata_2023-01.parquet"
ZONES_FILE_NAME = "taxi_zone_lookup.csv"

# --- Funções Auxiliares ---
def get_s3_client():
    """Retorna um cliente S3 configurado para o MinIO."""
    return boto3.client(
        's3', endpoint_url=MINIO_ENDPOINT, aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY, config=Config(signature_version='s3v4')
    )

def get_pandas_storage_options():
    """Retorna as opções de storage para o pandas ler/escrever no S3/MinIO."""
    return {
        "client_kwargs": {
            "endpoint_url": MINIO_ENDPOINT,
            "aws_access_key_id": MINIO_ACCESS_KEY,
            "aws_secret_access_key": MINIO_SECRET_KEY
        }
    }

# --- Tarefas do Pipeline ---
def create_buckets_if_not_exist():
    """Task 0: Garante que os buckets existem no storage de objetos."""
    s3_client = get_s3_client()
    for bucket_name in [BRONZE_BUCKET, SILVER_BUCKET, GOLD_BUCKET]:
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            logging.info(f"Bucket '{bucket_name}' já existe.")
        except:
            logging.info(f"Bucket '{bucket_name}' não encontrado. Criando...")
            s3_client.create_bucket(Bucket=bucket_name)

def extract_and_load_to_bronze(url: str, file_name: str, **kwargs):
    """Task 1 (Genérica): Extrai dados de uma URL e carrega na camada Bronze."""
    s3_client = get_s3_client()
    logging.info(f"Iniciando download de {url}")
    response = requests.get(url)
    response.raise_for_status()
    
    s3_key = f"raw/{file_name}"
    s3_client.put_object(Bucket=BRONZE_BUCKET, Key=s3_key, Body=response.content)
    logging.info(f"Carga na camada Bronze concluída em s3://{BRONZE_BUCKET}/{s3_key}")

def process_to_silver():
    """Task 2: Lê da Bronze, enriquece, limpa e salva na Silver."""
    storage_options = get_pandas_storage_options()
    
    # Ler os dois datasets da camada Bronze
    logging.info("Lendo dados de viagens e zonas da camada Bronze.")
    df_trips = pd.read_parquet(f"s3://{BRONZE_BUCKET}/raw/{TRIP_DATA_FILE_NAME}", storage_options=storage_options)
    df_zones = pd.read_csv(f"s3://{BRONZE_BUCKET}/raw/{ZONES_FILE_NAME}", storage_options=storage_options)

    # --- ENRIQUECIMENTO ---
    # 1. Renomear colunas da tabela de zonas para evitar conflitos no join
    df_zones.rename(columns={'LocationID': 'zone_id', 'Borough': 'borough', 'Zone': 'zone'}, inplace=True)
    
    # 2. Join para adicionar informações de embarque (Pickup)
    df_enriched = pd.merge(df_trips, df_zones, left_on='PULocationID', right_on='zone_id', how='left')
    df_enriched.rename(columns={'borough': 'pickup_borough', 'zone': 'pickup_zone'}, inplace=True)
    df_enriched.drop('zone_id', axis=1, inplace=True)
    
    # 3. Join para adicionar informações de desembarque (Dropoff)
    df_enriched = pd.merge(df_enriched, df_zones, left_on='DOLocationID', right_on='zone_id', how='left')
    df_enriched.rename(columns={'borough': 'dropoff_borough', 'zone': 'dropoff_zone'}, inplace=True)
    df_enriched.drop('zone_id', axis=1, inplace=True)
    logging.info("Join com dados de zona concluído.")

    # --- ENGENHARIA DE FEATURES ---
    df_enriched['tpep_pickup_datetime'] = pd.to_datetime(df_enriched['tpep_pickup_datetime'])
    df_enriched['tpep_dropoff_datetime'] = pd.to_datetime(df_enriched['tpep_dropoff_datetime'])
    
    # 1. Duração da viagem
    df_enriched['trip_duration_minutes'] = (df_enriched['tpep_dropoff_datetime'] - df_enriched['tpep_pickup_datetime']).dt.total_seconds() / 60
    
    # 2. Velocidade média (evitando divisão por zero)
    duration_hours = df_enriched['trip_duration_minutes'] / 60
    df_enriched['average_speed_mph'] = df_enriched['trip_distance'] / duration_hours.replace(0, pd.NA)

    # 3. Percentual da gorjeta
    df_enriched['tip_percentage'] = (df_enriched['tip_amount'] / df_enriched['fare_amount'].replace(0, pd.NA)) * 100

    # 4. Período do dia
    def get_time_of_day(hour):
        if 5 <= hour < 12: return 'Morning'
        if 12 <= hour < 17: return 'Afternoon'
        if 17 <= hour < 21: return 'Evening'
        return 'Night'
    df_enriched['time_of_day'] = df_enriched['tpep_pickup_datetime'].dt.hour.apply(get_time_of_day)
    logging.info("Engenharia de features concluída.")

    # --- LIMPEZA FINAL ---
    # Remove viagens com duração negativa ou excessiva e velocidades irreais
    df_cleaned = df_enriched[
        (df_enriched['trip_duration_minutes'] > 0) & 
        (df_enriched['trip_duration_minutes'] < 1440) & # Menos de 24h
        (df_enriched['fare_amount'] > 0) &
        (df_enriched['passenger_count'].between(1, 6)) &
        (df_enriched['average_speed_mph'] < 100) # Remove outliers de velocidade
    ]
    logging.info(f"Limpeza finalizada. Total de registros na camada Silver: {len(df_cleaned)}")

    # Salvar na camada Silver
    df_cleaned.to_parquet(f"s3://{SILVER_BUCKET}/processed/{TRIP_DATA_FILE_NAME}", index=False, storage_options=storage_options)
    logging.info("Carga na camada Silver concluída.")

def aggregate_to_gold(aggregation_type: str):
    """Task 3 (Genérica): Lê da Silver e cria uma tabela agregada específica na Gold."""
    storage_options = get_pandas_storage_options()
    df = pd.read_parquet(f"s3://{SILVER_BUCKET}/processed/{TRIP_DATA_FILE_NAME}", storage_options=storage_options)
    
    logging.info(f"Iniciando agregação para: {aggregation_type}")
    
    if aggregation_type == 'hourly_summary':
        df_agg = df.groupby(df['tpep_pickup_datetime'].dt.hour).agg(
            total_trips=('VendorID', 'count'),
            average_fare=('fare_amount', 'mean'),
            average_duration_mins=('trip_duration_minutes', 'mean')
        ).reset_index().rename(columns={'tpep_pickup_datetime': 'hour_of_day'})
        file_name = "gold_hourly_summary.csv"

    elif aggregation_type == 'borough_summary':
        df_agg = df.groupby(['pickup_borough', 'dropoff_borough']).agg(
            number_of_trips=('VendorID', 'count'),
            average_fare=('fare_amount', 'mean')
        ).reset_index().sort_values(by='number_of_trips', ascending=False)
        file_name = "gold_borough_summary.csv"

    elif aggregation_type == 'payment_type_summary':
        # Mapeando os códigos de pagamento para nomes legíveis
        payment_map = {1: 'Credit card', 2: 'Cash', 3: 'No charge', 4: 'Dispute', 5: 'Unknown', 6: 'Voided trip'}
        df['payment_type_name'] = df['payment_type'].map(payment_map)
        df_agg = df.groupby('payment_type_name').agg(
            total_trips=('VendorID', 'count'),
            average_tip_percentage=('tip_percentage', 'mean')
        ).reset_index()
        file_name = "gold_payment_type_summary.csv"
        
    else:
        raise ValueError("Tipo de agregação desconhecido.")
        
    df_agg.to_csv(f"s3://{GOLD_BUCKET}/aggregates/{file_name}", index=False, storage_options=storage_options)
    logging.info(f"Agregação '{aggregation_type}' salva em s3://{GOLD_BUCKET}/aggregates/{file_name}")

# --- Definição do DAG ---
with DAG(
    dag_id='batch_pipeline_taxi_nyc_enhanced',
    start_date=datetime(2024, 1, 1),
    schedule='@once',
    catchup=False,
    is_paused_upon_creation=False,  # This ensures the DAG starts enabled
    doc_md="""
    ### Pipeline de Batch Aprimorado
    Este pipeline realiza um ETL completo e mais complexo:
    - **Bronze**: Ingestão de dados de corridas e de zonas geográficas.
    - **Silver**: Limpeza, junção dos datasets e engenharia de features (duração, velocidade, etc.).
    - **Gold**: Criação de múltiplas tabelas agregadas para diferentes análises de negócio.
    """,
    tags=['data-engineering', 'batch', 'minio', 'enhanced'],
) as dag:
    
    create_buckets_task = PythonOperator(
        task_id='create_buckets_if_not_exist',
        python_callable=create_buckets_if_not_exist,
    )

    with TaskGroup("extract_and_load_bronze") as extract_group:
        extract_trip_data = PythonOperator(
            task_id='extract_trip_data',
            python_callable=extract_and_load_to_bronze,
            op_kwargs={'url': TRIP_DATA_URL, 'file_name': TRIP_DATA_FILE_NAME}
        )
        extract_zone_data = PythonOperator(
            task_id='extract_zone_data',
            python_callable=extract_and_load_to_bronze,
            op_kwargs={'url': ZONES_URL, 'file_name': ZONES_FILE_NAME}
        )
    
    process_to_silver_task = PythonOperator(
        task_id='process_to_silver',
        python_callable=process_to_silver,
    )

    with TaskGroup("aggregate_to_gold") as gold_group:
        aggregate_hourly = PythonOperator(
            task_id='aggregate_hourly_summary',
            python_callable=aggregate_to_gold,
            op_kwargs={'aggregation_type': 'hourly_summary'}
        )
        aggregate_borough = PythonOperator(
            task_id='aggregate_borough_summary',
            python_callable=aggregate_to_gold,
            op_kwargs={'aggregation_type': 'borough_summary'}
        )
        aggregate_payment = PythonOperator(
            task_id='aggregate_payment_type_summary',
            python_callable=aggregate_to_gold,
            op_kwargs={'aggregation_type': 'payment_type_summary'}
        )
        
    create_buckets_task >> extract_group >> process_to_silver_task >> gold_group