from datetime import datetime, timedelta, timezone
from airflow import DAG
from airflow.operators.python import PythonOperator
from mark.mark_tasks import run_scan

with DAG(
    dag_id='mark_elr_polling', schedule_interval='*/15 * * * *',
    start_date=datetime(2026, 11, 1, tzinfo=timezone(timedelta(hours=7))),
    catchup=False, max_active_runs=1, max_active_tasks=1,
    is_paused_upon_creation=True, tags=['mark'],
    default_args={'retries': 2, 'retry_delay': timedelta(minutes=2),
                  'execution_timeout': timedelta(minutes=10)},
) as dag:
    PythonOperator(task_id='scan', python_callable=run_scan,
                   op_kwargs={'path': '/api/scans', 'body': {'source': 'airflow'}},
                   do_xcom_push=False)
