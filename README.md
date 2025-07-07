# Projeto de Bloco: Arquitetura Lambda com Apache Airflow, MinIO, e Streaming com Kafka

Este projeto implementa uma Arquitetura Lambda completa para processamento de dados, combinando uma camada de batch (Apache Airflow + MinIO) com uma camada de velocidade (Apache Kafka + Redis). O pipeline é totalmente automatizado, não requerendo intervenção manual para sua execução.

## 🏗️ Arquitetura do Sistema

### Camada Batch (Serving Layer)
O pipeline batch é orquestrado pelo Airflow e executa automaticamente após a inicialização do sistema:

1. **Criação de Buckets**: Configura automaticamente os buckets necessários no MinIO.
2. **Extração e Carga (Bronze)**: Baixa os dados de táxi de NY e armazena no bucket `bronze`.
3. **Transformação (Silver)**: Processa os dados brutos e salva no bucket `silver`.
4. **Agregação (Gold)**: Calcula métricas de negócio e disponibiliza no bucket `gold`.

### Camada Speed (Real-time Layer)
A camada de velocidade processa eventos em tempo real usando Kafka e Redis:

1. **Producer**: Monitora novos dados no MinIO e envia eventos para o Kafka.
2. **Consumer**: Processa eventos em tempo real e atualiza métricas no Redis.
3. **Armazenamento**: Utiliza Redis para manter as métricas em tempo real atualizadas.

## 📋 Pré-requisitos

* Docker
* Docker Compose

## ⚙️ Configuração

1. **Clone o Repositório**:
```bash
git clone https://github.com/mprytolukinfnet/Miguel_Prytoluk_PB_2025_1.git
cd tp5_app
```

2. **Configure o Ambiente**:
Crie um arquivo `.env` na raiz do projeto:

```env
# Airflow
AIRFLOW_UID=50000

# MinIO Configuration
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Bucket Names
BRONZE_BUCKET=bronze-bucket
SILVER_BUCKET=silver-bucket
GOLD_BUCKET=gold-bucket
```

## 🚀 Como Executar

Execute o sistema completo com um único comando:

```bash
docker compose up
```

O sistema iniciará automaticamente:
- O Airflow DAG será ativado e executado automaticamente
- O producer Kafka começará a monitorar novos dados
- O consumer Kafka processará eventos em tempo real

## 🌐 Acessando os Serviços

- **Airflow**: http://localhost:8080 (usuário: `airflow`, senha: `airflow`)
- **MinIO Console**: http://localhost:9091 (usuário: `minioadmin`, senha: `minioadmin`)
- **Kafka**: Porta 29092 (interno), 9092 (externo)
- **Redis**: Porta 6379

## 📂 Estrutura do Projeto

```
/Miguel_Prytoluk_PB_2025_1
├── dags/
│   └── batch_pipeline_taxi_nyc.py
├── streaming/
│   ├── producer.py
│   ├── speed_consumer.py
│   ├── create_topic.py
│   └── requirements.txt
├── minio_setup_files/
│   └── setup.sh
├── .env
├── docker-compose.yaml
├── Dockerfile
├── streaming.Dockerfile
├── requirements.txt
└── trigger_dag.sh
```

## 🔄 Fluxo de Execução

1. **Inicialização**:
   - Os serviços Docker são iniciados
   - MinIO é configurado com os buckets necessários
   - O tópico Kafka é criado
   - O Airflow é inicializado e o DAG é ativado automaticamente

2. **Pipeline de Batch**:
   - O DAG é executado automaticamente após a inicialização
   - Os dados são processados através das camadas Bronze → Silver → Gold

3. **Pipeline de Speed**:
   - O producer monitora continuamente novos dados
   - Eventos são enviados para o Kafka
   - O consumer processa os eventos em tempo real
   - As métricas são atualizadas no Redis

## 📊 Monitoramento

- Use a UI do Airflow para monitorar o pipeline de batch
- Verifique os dados processados no Console do MinIO
- Monitore as métricas em tempo real no Redis