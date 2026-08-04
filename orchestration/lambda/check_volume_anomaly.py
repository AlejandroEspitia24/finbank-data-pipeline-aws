"""Lambda invocada por la state machine justo después de la Ingesta Bronze.

Compara el volumen total de registros ingeridos en la ejecución actual
contra el promedio de las últimas 7 ejecuciones diarias anteriores. Si la
desviación supera el umbral configurado (por defecto 30%), publica una
alerta en el topic SNS del pipeline.

Decisión de diseño: esta validación es informativa, no bloqueante. Si el
volumen es anómalo, se notifica pero el pipeline continúa hacia Silver y
Gold — un volumen bajo o alto no es necesariamente un dato corrupto (puede
ser una carga incremental legítimamente pequeña), así que la decisión de
detener el pipeline se deja a una persona, no a esta función automática.

Fuente de datos: los logs de ejecución que cada Glue Job ya escribe en
s3://{bronze_bucket}/_control/ingestion_log/layer=bronze/dt=YYYY-MM-DD/
(ver pipelines/common/glue_utils.py::write_run_log). No se crea ninguna
tabla ni almacenamiento nuevo para esto — se reutiliza lo que Bronze ya
produce como evidencia de auditoría.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns = boto3.client("sns")

BRONZE_BUCKET = os.environ["BRONZE_BUCKET"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
THRESHOLD_PCT = float(os.environ.get("VOLUME_ANOMALY_THRESHOLD_PCT", "30"))
LOOKBACK_DAYS = int(os.environ.get("VOLUME_ANOMALY_LOOKBACK_DAYS", "7"))


def _total_records_for_date(date_str: str) -> int:
    """Suma records_processed de todos los logs de ingesta Bronze de un día."""
    prefix = f"_control/ingestion_log/layer=bronze/dt={date_str}/"
    total = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BRONZE_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            body = s3.get_object(Bucket=BRONZE_BUCKET, Key=obj["Key"])["Body"].read()
            record = json.loads(body)
            total += record.get("records_processed", 0)
    return total


def handler(event, context):
    today = datetime.now(timezone.utc).date()
    today_total = _total_records_for_date(today.isoformat())

    history = []
    for i in range(1, LOOKBACK_DAYS + 1):
        day = (today - timedelta(days=i)).isoformat()
        day_total = _total_records_for_date(day)
        if day_total > 0:
            history.append(day_total)

    result = {
        "date": today.isoformat(),
        "records_today": today_total,
        "history_days_used": len(history),
        "anomaly_detected": False,
    }

    if not history:
        logger.info("Sin historial previo (primera ejecución o menos de %s días de datos). "
                    "No se puede calcular desviación, se omite la validación.", LOOKBACK_DAYS)
        return result

    avg_history = sum(history) / len(history)
    result["avg_last_n_days"] = avg_history

    if avg_history == 0:
        return result

    deviation_pct = abs(today_total - avg_history) / avg_history * 100
    result["deviation_pct"] = round(deviation_pct, 2)

    if deviation_pct > THRESHOLD_PCT:
        result["anomaly_detected"] = True
        message = (
            f"[ALERTA] Volumen anómalo detectado en la ingesta Bronze de FinBank.\n\n"
            f"Fecha: {today.isoformat()}\n"
            f"Registros ingeridos hoy: {today_total}\n"
            f"Promedio últimos {len(history)} días con datos: {avg_history:.0f}\n"
            f"Desviación: {deviation_pct:.1f}% (umbral configurado: {THRESHOLD_PCT}%)\n\n"
            f"El pipeline continúa su ejecución normal (Silver y Gold). Esta alerta es "
            f"informativa para que un humano revise si el cambio de volumen es esperado."
        )
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="FinBank Pipeline — Alerta de volumen anómalo",
            Message=message,
        )
        logger.warning("Anomalía de volumen detectada: %.1f%% de desviación", deviation_pct)
    else:
        logger.info("Volumen dentro de rango normal: %.1f%% de desviación", deviation_pct)

    return result
