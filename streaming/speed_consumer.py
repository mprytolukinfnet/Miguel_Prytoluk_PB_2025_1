# Este é o coração da camada Speed.
# Ele consome os dados do Kafka, faz uma agregação em tempo real e salva no Redis.
from kafka import KafkaConsumer
import json
import redis
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

r = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
logging.info("Conectado ao Redis.")

consumer = KafkaConsumer(
    'taxi_trips',
    bootstrap_servers='kafka:29092',
    auto_offset_reset='earliest',
    group_id='speed-layer-group',
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

logging.info("Consumer da Camada Speed iniciado. Aguardando mensagens...")
for message in consumer:
    try:
        trip = message.value
        vendor_id = trip.get('VendorID')
        fare = float(trip.get('fare_amount', 0))
        
        if vendor_id and fare > 0:
            redis_key = f"realtime_fare:vendor:{vendor_id}"
            # Agregação atômica no Redis
            current_fare = r.incrbyfloat(redis_key, fare)
            logging.info(f"<-- Mensagem recebida: VendorID={vendor_id}. Faturamento atualizado para ${current_fare:.2f}")

    except Exception as e:
        logging.error(f"Erro ao processar mensagem: {e}")