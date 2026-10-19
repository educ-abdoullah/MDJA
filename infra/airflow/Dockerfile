FROM apache/airflow:3.3.2-python3.12
COPY --chown=airflow:root requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" \
    -r /opt/airflow/requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt"
COPY --chown=airflow:root src /opt/airflow/src
RUN mkdir -p /opt/airflow/auth && chmod 0770 /opt/airflow/auth
ENV PYTHONPATH=/opt/airflow/src
