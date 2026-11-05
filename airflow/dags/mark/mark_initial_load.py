from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from airflow import DAG
from airflow.operators.python import PythonOperator
from mark.mark_tasks import run_scan

with DAG(
    dag_id='mark_initial_load', schedule_interval=None,
    start_date=datetime(2026, 11, 1, tzinfo=ZoneInfo('Asia/Bangkok')),
    catchup=False, max_active_runs=1, max_active_tasks=1,
    is_paused_upon_creation=True, tags=['mark'],
    default_args={'retries': 0, 'execution_timeout': timedelta(minutes=60)},
) as dag:
    PythonOperator(task_id='initial_load', python_callable=run_scan,
                   op_kwargs={'path': '/api/scans', 'body': {'source': 'initial'}},
                   do_xcom_push=False)
