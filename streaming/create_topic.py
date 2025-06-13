# Este script cria o tópico no Kafka para receber as mensagens.
# Deve ser executado uma única vez.
from kafka.admin import KafkaAdminClient, NewTopic
print("Tentando criar o tópico Kafka 'taxi_trips'...")
try:
    admin_client = KafkaAdminClient(
        bootstrap_servers="kafka:29092",
        client_id='test'
    )
    topic_list = [NewTopic(name="taxi_trips", num_partitions=1, replication_factor=1)]
    admin_client.create_topics(new_topics=topic_list, validate_only=False)
    print("Tópico 'taxi_trips' criado com sucesso ou já existente.")
except Exception as e:
    print(f"Falha ao criar o tópico: {e}")