"""Lambda invocada por la state machine justo después de que Gold termina
exitosamente. Recopila las métricas que el enunciado exige en el reporte
diario de éxito: registros procesados por capa, tiempo total de ejecución
y número de alertas/registros rechazados por calidad — para que Step
Functions pueda armar un mensaje de SNS con datos reales, no un texto
genérico de "todo salió bien".

No publica nada por sí misma: solo calcula y devuelve el resumen; quien
publica a SNS es el estado `NotificarExito` de la state machine (mismo
patrón que `check_volume_anomaly.py`, que tampoco decide bloquear el
pipeline por sí solo).
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

BRONZE_BUCKET = os.environ["BRONZE_BUCKET"]
SILVER_BUCKET = os.environ["SILVER_BUCKET"]
GOLD_BUCKET = os.environ["GOLD_BUCKET"]


def _sum_records_processed(bucket: str, layer: str, date_str: str) -> int:
    prefix = f"_control/ingestion_log/layer={layer}/dt={date_str}/"
    total = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            total += json.loads(body).get("records_processed", 0)
    return total


def _latest_object(bucket: str, prefix: str):
    """Devuelve el contenido del objeto más reciente bajo un prefijo, o None."""
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    contents = resp.get("Contents", [])
    if not contents:
        return None
    latest = max(contents, key=lambda o: o["LastModified"])
    body = s3.get_object(Bucket=bucket, Key=latest["Key"])["Body"].read()
    return json.loads(body)


def handler(event, context):
    today = datetime.now(timezone.utc).date().isoformat()

    bronze_records = _sum_records_processed(BRONZE_BUCKET, "bronze", today)
    silver_records = _sum_records_processed(SILVER_BUCKET, "silver", today)
    gold_records = _sum_records_processed(GOLD_BUCKET, "gold", today)

    # "Registros rechazados por calidad": el total de registros que Silver
    # movió a la tabla de errores en ejecuciones de hoy (violaciones de FK +
    # reglas de negocio), tomado del reporte de calidad más reciente del día.
    quality_report = _latest_object(SILVER_BUCKET, f"_control/quality_report/layer=silver/dt={today}/")
    quality_rejected_records = 0
    if quality_report:
        quality_rejected_records = sum(
            t.get("rejected", 0) for t in quality_report.get("tables", {}).values()
        )

    # "Alertas de calidad": verificaciones automatizadas que fallaron en la
    # corrida de DQ checks más reciente del día (0 si las 5 verificaciones
    # pasaron, como es el caso esperado en una ejecución sana).
    dq_report = _latest_object(SILVER_BUCKET, f"_control/dq_checks/dt={today}/")
    dq_checks_failed = 0
    if dq_report:
        dq_checks_failed = sum(1 for c in dq_report.get("checks", []) if not c.get("passed", True))

    execution_start_time = event.get("execution_start_time")
    execution_duration_seconds = None
    if execution_start_time:
        start = datetime.fromisoformat(execution_start_time.replace("Z", "+00:00"))
        execution_duration_seconds = round((datetime.now(timezone.utc) - start).total_seconds())

    summary = {
        "date": today,
        "bronze_records": bronze_records,
        "silver_records": silver_records,
        "gold_records": gold_records,
        "quality_rejected_records": quality_rejected_records,
        "dq_checks_failed": dq_checks_failed,
        "execution_duration_seconds": execution_duration_seconds,
    }
    logger.info("Resumen de ejecucion: %s", json.dumps(summary))
    return summary
