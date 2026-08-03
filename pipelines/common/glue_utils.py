"""Utilidades compartidas por los Glue Jobs de las tres capas Medallion
(Bronze, Silver, Gold). Se sube a S3 y se referencia desde cada job vía
--extra-py-files, en vez de duplicar esta lógica en cada script.
"""

import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def get_watermark(bucket: str, table: str) -> str | None:
    """Lee la última marca de agua guardada para una tabla en modo incremental.

    Devuelve None si no existe (primera ejecución -> full load).
    """
    s3 = boto3.client("s3")
    key = f"_control/watermarks/{table}.json"
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(obj["Body"].read())
        return data.get("last_watermark")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def save_watermark(bucket: str, table: str, watermark: str, batch_id: str) -> None:
    s3 = boto3.client("s3")
    key = f"_control/watermarks/{table}.json"
    body = json.dumps({
        "last_watermark": watermark,
        "last_batch_id": batch_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
    logger.info("Watermark actualizado para %s: %s", table, watermark)


def write_run_log(bucket: str, layer: str, table: str, batch_id: str, status: str,
                   records_processed: int = 0, duration_seconds: float = 0.0,
                   output_size_bytes: int = 0, error_message: str = "") -> None:
    """Escribe un registro de log de ejecución por tabla, en formato JSON,
    en s3://{bucket}/_control/ingestion_log/. Es un requisito explícito del
    enunciado ("registrar un log de cada ejecución de ingesta").
    """
    s3 = boto3.client("s3")
    now = datetime.now(timezone.utc)
    key = f"_control/ingestion_log/layer={layer}/dt={now:%Y-%m-%d}/{batch_id}_{table}.json"
    body = json.dumps({
        "layer": layer,
        "table": table,
        "batch_id": batch_id,
        "status": status,
        "records_processed": records_processed,
        "duration_seconds": round(duration_seconds, 2),
        "output_size_bytes": output_size_bytes,
        "timestamp": now.isoformat(),
        "error_message": error_message,
    })
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
    logger.info("Log de ejecucion escrito: %s (status=%s)", key, status)


def s3_prefix_size(bucket: str, prefix: str) -> int:
    """Suma el tamaño en bytes de todos los objetos bajo un prefijo S3 —
    usado para reportar el tamaño del archivo generado en el log de ingesta.
    """
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            total += obj["Size"]
    return total


def write_error_record(bucket: str, layer: str, table: str, batch_id: str,
                        record_id: str, reason: str) -> None:
    """Tabla de errores del pipeline: un registro JSON por fila rechazada,
    con el motivo documentado (requisito de la capa Silver, reutilizado
    también por Bronze/Gold si aplica).
    """
    s3 = boto3.client("s3")
    now = datetime.now(timezone.utc)
    key = f"_control/pipeline_errors/layer={layer}/dt={now:%Y-%m-%d}/{batch_id}_{table}_{record_id}.json"
    body = json.dumps({
        "layer": layer,
        "table": table,
        "batch_id": batch_id,
        "record_id": record_id,
        "reason": reason,
        "timestamp": now.isoformat(),
    })
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))


def write_quality_report(bucket: str, layer: str, batch_id: str, report: dict) -> None:
    """Reporte de calidad de datos por ejecución: % de nulos por columna,
    registros rechazados y % de registros conformes por tabla. Requisito
    explícito de la capa Silver.
    """
    s3 = boto3.client("s3")
    now = datetime.now(timezone.utc)
    key = f"_control/quality_report/layer={layer}/dt={now:%Y-%m-%d}/{batch_id}.json"
    body = json.dumps({"layer": layer, "batch_id": batch_id, "timestamp": now.isoformat(), "tables": report}, indent=2)
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
    logger.info("Reporte de calidad escrito: %s", key)


def write_dq_check_report(bucket: str, batch_id: str, checks: list) -> None:
    """Resultado de las verificaciones automatizadas de calidad de datos
    (aprobado/fallido por chequeo), requisito transversal del pipeline.
    """
    s3 = boto3.client("s3")
    now = datetime.now(timezone.utc)
    all_passed = all(c["passed"] for c in checks)
    key = f"_control/dq_checks/dt={now:%Y-%m-%d}/{batch_id}.json"
    body = json.dumps({
        "batch_id": batch_id,
        "timestamp": now.isoformat(),
        "overall_status": "PASSED" if all_passed else "FAILED",
        "checks": checks,
    }, indent=2)
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
    logger.info("Reporte de calidad (DQ checks) escrito: %s (overall=%s)",
                key, "PASSED" if all_passed else "FAILED")
