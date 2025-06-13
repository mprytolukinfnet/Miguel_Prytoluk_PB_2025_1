# Este Dockerfile constrói uma imagem para nossos aplicativos Python de streaming.
FROM python:3.9-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia os scripts e o arquivo de requisitos para dentro da imagem
COPY ./streaming /app

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt