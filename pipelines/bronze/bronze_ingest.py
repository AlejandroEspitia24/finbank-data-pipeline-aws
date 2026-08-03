"""Glue Job — Capa Bronze: ingesta cruda desde RDS PostgreSQL hacia S3.

Copia los datos de origen con el mínimo de transformaciones posible,
preservando el esquema original de cada tabla sin modificaciones. Agrega
tres columnas de metadatos de auditoría y particiona por fecha de ingesta
(año/mes/día). Ver pipelines/bronze/README.md para las decisiones de diseño
(watermark de incremental, idempotencia, manejo de errores).
"""

import sys
import time
import uuid
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

from glue_utils import get_watermark, s3_prefix_size, save_watermark, write_run_log
from table_config import TABLES

SOURCE_SYSTEM = "RDS_FINBANK_CORE"


def read_table(spark, jdbc_conf, table, mode, watermark_col, bronze_bucket, db_name):
    query = f"SELECT * FROM {table}"
    watermark_before = None
    if mode == "incremental":
        watermark_before = get_watermark(bronze_bucket, table)
        if watermark_before:
            query = f"SELECT * FROM {table} WHERE {watermark_col} > '{watermark_before}'"

    # extract_jdbc_conf() devuelve la URL recortada hasta host:puerto, sin el
    # nombre de la base de datos (causa real de "PSQLException: Unable to
    # parse URL" en las primeras corridas). En vez de confiar en el formato
    # exacto que devuelve Glue, construimos nosotros el sufijo "/db_name" con
    # un valor que ya conocemos (parámetro del job). La URL nunca contiene el
    # password (va en una opción JDBC separada), así que registrarla en el
    # log no expone ningún secreto.
    jdbc_url = jdbc_conf["url"]
    if not jdbc_url.startswith("jdbc:"):
        jdbc_url = f"jdbc:{jdbc_url}"
    if not jdbc_url.rstrip("/").endswith(f"/{db_name}"):
        jdbc_url = f"{jdbc_url.rstrip('/')}/{db_name}"
    print(f"[bronze] Conectando con URL JDBC: {jdbc_url}")

    df = (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("user", jdbc_conf["user"])
        .option("password", jdbc_conf["password"])
        .option("driver", "org.postgresql.Driver")
        .option("query", query)
        .load()
    )
    return df


def main():
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "rds_connection_name", "bronze_bucket", "db_name"])
    batch_id = str(uuid.uuid4())

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    # Overwrite dinámico: al reescribir, solo se reemplaza la partición
    # (año/mes/día) que este job produce, sin tocar particiones históricas.
    # Es lo que garantiza idempotencia: correr el job dos veces el mismo día
    # sobre los mismos datos no genera duplicados ni borra días anteriores.
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    jdbc_conf = glue_context.extract_jdbc_conf(args["rds_connection_name"])
    bronze_bucket = args["bronze_bucket"]

    now = datetime.now(timezone.utc)
    anio, mes, dia = f"{now:%Y}", f"{now:%m}", f"{now:%d}"

    for table, cfg in TABLES.items():
        start = time.time()
        try:
            df = read_table(spark, jdbc_conf, table, cfg["mode"], cfg["watermark_col"], bronze_bucket, args["db_name"])
            record_count = df.count()

            if record_count == 0:
                write_run_log(bronze_bucket, "bronze", table, batch_id, "SUCCESS_NO_NEW_DATA",
                              0, time.time() - start)
                continue

            df_audited = (
                df.withColumn("_ingestion_timestamp", F.current_timestamp())
                  .withColumn("_source_system", F.lit(SOURCE_SYSTEM))
                  .withColumn("_batch_id", F.lit(batch_id))
                  .withColumn("anio", F.lit(anio))
                  .withColumn("mes", F.lit(mes))
                  .withColumn("dia", F.lit(dia))
            )

            output_path = f"s3://{bronze_bucket}/{table}/"
            (
                df_audited.write
                .mode("overwrite")
                .partitionBy("anio", "mes", "dia")
                .parquet(output_path)
            )

            output_prefix = f"{table}/anio={anio}/mes={mes}/dia={dia}/"
            size_bytes = s3_prefix_size(bronze_bucket, output_prefix)

            if cfg["mode"] == "incremental":
                new_watermark = df.agg(F.max(cfg["watermark_col"])).collect()[0][0]
                if new_watermark:
                    save_watermark(bronze_bucket, table, str(new_watermark), batch_id)

            write_run_log(bronze_bucket, "bronze", table, batch_id, "SUCCESS",
                          record_count, time.time() - start, size_bytes)

        except Exception as e:
            # No relanzamos la excepción: una tabla fallida no debe
            # interrumpir la ingesta de las demás tablas (requisito de
            # manejo de errores del enunciado).
            write_run_log(bronze_bucket, "bronze", table, batch_id, "FAILED",
                          0, time.time() - start, 0, str(e))
            continue

    job.commit()


if __name__ == "__main__":
    main()
