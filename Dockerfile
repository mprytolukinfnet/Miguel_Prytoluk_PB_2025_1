FROM apache/airflow:2.9.2

USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    netcat-traditional && \
    apt-get clean
USER airflow

COPY requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt