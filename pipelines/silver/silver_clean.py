"""Glue Job — Capa Silver: limpieza, conformación y calidad de datos.

Lee el snapshot más reciente de cada tabla desde Bronze y aplica:
deduplicación, descarte de registros con campos críticos nulos,
estandarización de tipos, validación de integridad referencial,
enmascaramiento de PII, imputación de nulos documentada por columna, y el
cálculo de `ind_sospechoso` (detección de transacciones atípicas).

Escribe: tablas limpias en el bucket Silver, una tabla de errores unificada
(`_errors/`), un reporte de calidad por ejecución (`_control/quality_report/`)
y el resultado de 5 verificaciones automatizadas (`_control/dq_checks/`).
Ver pipelines/silver/README.md para el detalle de cada decisión.
"""

import sys
import time
import uuid
from functools import reduce

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from glue_utils import write_dq_check_report, write_quality_report, write_run_log
from table_config import TABLES

DIMENSION_ORDER = ["tb_productos_cat", "tb_sucursales_red", "tb_clientes_core"]
FACT_ORDER = ["tb_mov_financieros", "tb_obligaciones", "tb_comisiones_log"]


def load_latest_snapshot(spark, bronze_bucket, table, cfg):
    """full: solo la última partición de ingesta (recarga completa cada vez).
    incremental: todas las particiones acumuladas (histórico completo)."""
    df = spark.read.parquet(f"s3://{bronze_bucket}/{table}/")
    if cfg["mode"] == "full":
        latest = df.select(F.concat_ws("-", "anio", "mes", "dia").alias("d")).agg(F.max("d")).collect()[0][0]
        anio, mes, dia = latest.split("-")
        df = df.filter((F.col("anio") == anio) & (F.col("mes") == mes) & (F.col("dia") == dia))
    return df.drop("anio", "mes", "dia", "_ingestion_timestamp", "_source_system", "_batch_id")


def null_percentages(df, columns):
    total = df.count()
    if total == 0:
        return {c: 0.0 for c in columns}
    exprs = [F.round(F.sum(F.when(F.col(c).isNull(), 1).otherwise(0)) / total * 100, 2).alias(c) for c in columns]
    row = df.select(exprs).collect()[0]
    return {c: float(row[c]) for c in columns}


def trim_strings(df):
    for field in df.schema.fields:
        if field.dataType.typeName() == "string":
            df = df.withColumn(field.name, F.trim(F.col(field.name)))
    return df


def dedupe_and_require(df, pk, required_cols):
    df = trim_strings(df)
    df = df.dropDuplicates()          # duplicados exactos (fila completa) — cubre la anomalía intencional de Fase 1
    df = df.dropDuplicates([pk])      # duplicados por llave primaria aunque alguna otra columna difiera
    for col in required_cols:
        df = df.filter(F.col(col).isNotNull())
    return df


def mask_pii(df, table):
    """Solo tb_clientes_core y tb_mov_financieros tienen columnas PII en
    este modelo. num_doc / num_cuenta se hashean (SHA-256, irreversible);
    los nombres se enmascaran parcialmente (se conserva la inicial para
    trazabilidad visual sin exponer el nombre completo)."""
    if table == "tb_clientes_core":
        df = (
            df.withColumn("num_doc_hash", F.sha2(F.col("num_doc").cast("string"), 256))
              .withColumn("nomb_cli", F.when(F.col("nomb_cli").isNotNull(),
                                              F.concat(F.substring("nomb_cli", 1, 1), F.lit("***"))))
              .withColumn("apell_cli", F.when(F.col("apell_cli").isNotNull(),
                                               F.concat(F.substring("apell_cli", 1, 1), F.lit("***"))))
              .drop("num_doc")
        )
    elif table == "tb_mov_financieros":
        df = df.withColumn("num_cuenta_hash", F.sha2(F.col("num_cuenta").cast("string"), 256)).drop("num_cuenta")
    return df


def impute_nulls(df, table):
    """Estrategia de nulos documentada por tabla/columna. Cada imputación
    agrega un indicador binario <columna>_imputado, para que Gold pueda
    distinguir un valor observado de uno completado."""
    if table == "tb_clientes_core":
        median_score = df.approxQuantile("score_buro", [0.5], 0.01)
        median_score = median_score[0] if median_score else 0
        df = (
            df.withColumn("depto_res_imputado", F.col("depto_res").isNull())
              .withColumn("depto_res", F.coalesce(F.col("depto_res"), F.lit("SIN_INFORMAR")))
              .withColumn("canal_adquis_imputado", F.col("canal_adquis").isNull())
              .withColumn("canal_adquis", F.coalesce(F.col("canal_adquis"), F.lit("DESCONOCIDO")))
              .withColumn("score_buro_imputado", F.col("score_buro").isNull())
              .withColumn("score_buro", F.coalesce(F.col("score_buro"), F.lit(median_score)))
        )
    elif table == "tb_mov_financieros":
        df = (
            df.withColumn("id_dispositivo_imputado", F.col("id_dispositivo").isNull())
              .withColumn("id_dispositivo", F.coalesce(F.col("id_dispositivo"), F.lit("NO_DISPONIBLE")))
              .withColumn("cod_canal_imputado", F.col("cod_canal").isNull())
              .withColumn("cod_canal", F.coalesce(F.col("cod_canal"), F.lit("DESCONOCIDO")))
        )
    elif table == "tb_obligaciones":
        df = (
            df.withColumn("num_cuotas_pend_imputado", F.col("num_cuotas_pend").isNull())
              .withColumn("num_cuotas_pend", F.coalesce(
                  F.col("num_cuotas_pend"),
                  F.when(F.col("vr_cuota") > 0, F.round(F.col("sdo_capital") / F.col("vr_cuota"))).otherwise(F.lit(0)),
              ))
        )
    elif table == "tb_comisiones_log":
        df = (
            df.withColumn("tip_comision_imputado", F.col("tip_comision").isNull())
              .withColumn("tip_comision", F.coalesce(F.col("tip_comision"), F.lit("NO_CLASIFICADA")))
        )
    return df


def validate_fk(df, table, cfg, dim_lookups, batch_id):
    """Deja pasar solo los registros cuyas FK existen en las dimensiones ya
    limpias. Los que no, se separan a la tabla de errores con el motivo."""
    if "fk" not in cfg:
        return df, None
    good = df
    for fk_col, parent_table in cfg["fk"].items():
        good = good.join(dim_lookups[parent_table], good[fk_col] == dim_lookups[parent_table]["_pk"], "left_semi")
    bad = df.join(good.select(cfg["pk"]).distinct(), on=cfg["pk"], how="left_anti")

    err_df = None
    if bad.count() > 0:
        err_df = (
            bad.select(F.col(cfg["pk"]).cast("string").alias("record_id"))
               .withColumn("table_name", F.lit(table))
               .withColumn("reason", F.lit("FK_VIOLATION_ID_INEXISTENTE"))
               .withColumn("batch_id", F.lit(batch_id))
               .withColumn("layer", F.lit("silver"))
               .withColumn("timestamp", F.current_timestamp())
        )
    return good, err_df


def business_rule_errors(df, table, batch_id):
    """Validaciones de negocio adicionales que también rechazan a la tabla
    de errores — no son violaciones de FK, pero son igual de inválidas para
    Silver, la capa de confianza analítica."""
    if table == "tb_mov_financieros":
        # Anomalía intencional de Fase 1: fechas fuera del rango histórico esperado.
        bad = df.filter((F.col("fec_mov") > F.current_date()) | (F.col("fec_mov") < F.date_sub(F.current_date(), 400)))
        reason = "FECHA_FEC_MOV_FUERA_DE_RANGO"
        pk = "id_mov"
    elif table == "tb_obligaciones":
        # Anomalía intencional de Fase 1: inconsistencia vr_desembolsado > vr_aprobado.
        bad = df.filter(F.col("vr_desembolsado") > F.col("vr_aprobado"))
        reason = "VR_DESEMBOLSADO_MAYOR_A_VR_APROBADO"
        pk = "id_oblig"
    else:
        return df, None

    good = df.join(bad.select(pk).distinct(), on=pk, how="left_anti")
    err_df = None
    if bad.count() > 0:
        err_df = (
            bad.select(F.col(pk).cast("string").alias("record_id"))
               .withColumn("table_name", F.lit(table))
               .withColumn("reason", F.lit(reason))
               .withColumn("batch_id", F.lit(batch_id))
               .withColumn("layer", F.lit("silver"))
               .withColumn("timestamp", F.current_timestamp())
        )
    return good, err_df


def compute_ind_sospechoso(df):
    """Marca una transacción como sospechosa cuando su vr_mov supera en más
    de 3 desviaciones estándar el promedio de los 30 días PREVIOS del mismo
    cliente (ventana [-30d, -1d], excluyendo el día actual de la transacción
    para no comparar un valor contra sí mismo)."""
    w = (
        Window.partitionBy("id_cli")
        .orderBy(F.col("fec_mov").cast("timestamp").cast("long"))
        .rangeBetween(-30 * 86400, -1)
    )
    df = df.withColumn("_avg_30d", F.avg("vr_mov").over(w)).withColumn("_std_30d", F.stddev("vr_mov").over(w))
    df = df.withColumn(
        "ind_sospechoso",
        F.when(F.col("_std_30d").isNotNull() & (F.col("vr_mov") > F.col("_avg_30d") + 3 * F.col("_std_30d")), True)
         .otherwise(False),
    )
    return df.drop("_avg_30d", "_std_30d")


def run_dq_checks(tables_clean, dim_lookups):
    """Cinco verificaciones automatizadas de calidad de datos sobre las
    tablas ya limpias de Silver, tal como exige el enunciado."""
    checks = []

    for table, cfg in TABLES.items():
        dup = tables_clean[table].groupBy(cfg["pk"]).count().filter("count > 1").count()
        checks.append({"name": f"unicidad_pk_{table}", "passed": dup == 0,
                        "details": f"{dup} llaves primarias duplicadas"})

    null_required = 0
    for table, cfg in TABLES.items():
        for col in cfg["required"]:
            null_required += tables_clean[table].filter(F.col(col).isNull()).count()
    checks.append({"name": "sin_nulos_en_columnas_criticas", "passed": null_required == 0,
                    "details": f"{null_required} nulos encontrados en columnas requeridas"})

    orphan_total = 0
    for table, cfg in TABLES.items():
        if "fk" not in cfg:
            continue
        df = tables_clean[table]
        for fk_col, parent in cfg["fk"].items():
            orphan_total += df.join(dim_lookups[parent], df[fk_col] == dim_lookups[parent]["_pk"], "left_anti").count()
    checks.append({"name": "integridad_referencial_fk", "passed": orphan_total == 0,
                    "details": f"{orphan_total} registros con FK huérfana"})

    neg_amounts = tables_clean["tb_mov_financieros"].filter(F.col("vr_mov") <= 0).count()
    checks.append({"name": "montos_transaccion_positivos", "passed": neg_amounts == 0,
                    "details": f"{neg_amounts} transacciones con vr_mov <= 0"})

    bad_dates = tables_clean["tb_mov_financieros"].filter(
        (F.col("fec_mov") > F.current_date()) | (F.col("fec_mov") < F.date_sub(F.current_date(), 400))
    ).count()
    checks.append({"name": "fechas_movimiento_en_rango", "passed": bad_dates == 0,
                    "details": f"{bad_dates} transacciones con fecha fuera de rango"})

    return checks


def main():
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "bronze_bucket", "silver_bucket"])
    batch_id = str(uuid.uuid4())

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    bronze_bucket, silver_bucket = args["bronze_bucket"], args["silver_bucket"]

    quality_report = {}
    error_frames = []
    tables_clean = {}
    dim_lookups = {}

    # 1) Dimensiones primero: las tablas de hechos dependen de sus llaves ya limpias.
    for table in DIMENSION_ORDER:
        start = time.time()
        cfg = TABLES[table]
        raw = load_latest_snapshot(spark, bronze_bucket, table, cfg)
        quality_report[table] = {"pct_nulos_pre_limpieza": null_percentages(raw, raw.columns)}
        n_before = raw.count()

        clean = dedupe_and_require(raw, cfg["pk"], cfg["required"])
        clean = impute_nulls(clean, table)
        clean = mask_pii(clean, table)

        n_after = clean.count()
        quality_report[table].update({
            "registros_entrada": n_before,
            "registros_conformes": n_after,
            "registros_rechazados": n_before - n_after,
            "pct_conformes": round(n_after / n_before * 100, 2) if n_before else 0.0,
        })

        tables_clean[table] = clean
        dim_lookups[table] = clean.select(F.col(cfg["pk"]).alias("_pk")).distinct()
        clean.write.mode("overwrite").parquet(f"s3://{silver_bucket}/{table}/")
        write_run_log(silver_bucket, "silver", table, batch_id, "SUCCESS", n_after, time.time() - start)

    # 2) Tablas de hechos: FK, reglas de negocio, PII, ind_sospechoso.
    for table in FACT_ORDER:
        start = time.time()
        cfg = TABLES[table]
        raw = load_latest_snapshot(spark, bronze_bucket, table, cfg)
        quality_report[table] = {"pct_nulos_pre_limpieza": null_percentages(raw, raw.columns)}
        n_before = raw.count()

        clean = dedupe_and_require(raw, cfg["pk"], cfg["required"])
        clean, err_fk = validate_fk(clean, table, cfg, dim_lookups, batch_id)
        clean, err_biz = business_rule_errors(clean, table, batch_id)
        clean = impute_nulls(clean, table)
        clean = mask_pii(clean, table)

        if table == "tb_mov_financieros":
            clean = compute_ind_sospechoso(clean)

        for err in (err_fk, err_biz):
            if err is not None:
                error_frames.append(err)

        n_after = clean.count()
        quality_report[table].update({
            "registros_entrada": n_before,
            "registros_conformes": n_after,
            "registros_rechazados": n_before - n_after,
            "pct_conformes": round(n_after / n_before * 100, 2) if n_before else 0.0,
        })

        tables_clean[table] = clean
        clean.write.mode("overwrite").parquet(f"s3://{silver_bucket}/{table}/")
        write_run_log(silver_bucket, "silver", table, batch_id, "SUCCESS", n_after, time.time() - start)

    # 3) Tabla de errores unificada.
    if error_frames:
        errors_df = reduce(lambda a, b: a.unionByName(b), error_frames)
        errors_df.write.mode("append").partitionBy("table_name").parquet(f"s3://{silver_bucket}/_errors/")
        print(f"[silver] {errors_df.count()} registros enviados a la tabla de errores")
    else:
        print("[silver] Sin registros rechazados en esta ejecucion")

    # 4) Reporte de calidad y 5 verificaciones automatizadas.
    write_quality_report(silver_bucket, "silver", batch_id, quality_report)
    checks = run_dq_checks(tables_clean, dim_lookups)
    write_dq_check_report(silver_bucket, batch_id, checks)
    for c in checks:
        print(f"[silver] DQ check '{c['name']}': {'PASSED' if c['passed'] else 'FAILED'} — {c['details']}")

    job.commit()


if __name__ == "__main__":
    main()
