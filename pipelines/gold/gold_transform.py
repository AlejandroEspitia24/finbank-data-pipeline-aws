"""Glue Job — Capa Gold: modelo dimensional y reglas de negocio de FinBank.

Lee las tablas limpias de Silver y construye el modelo dimensional completo
(4 dimensiones, 3 tablas de hechos, 1 tabla de KPIs ejecutivos) aplicando
las reglas de negocio del escenario Banca definidas en docs/PLAN.md.
Ver pipelines/gold/README.md para el detalle de cada regla, el linaje de
los campos calculados, y los supuestos documentados.
"""

import sys
import time
import uuid

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from glue_utils import write_run_log
from table_config import TABLES

# Supuesto documentado: el dataset no expone una tasa de cambio real: se usa
# una tasa fija COP -> USD para la conversión de montos, tal como exige la
# regla de negocio de fact_transacciones. Ver pipelines/gold/README.md.
USD_COP_RATE = 4000

# Tabla de provisión regulatoria estimada por bucket de mora (porcentaje
# sobre el saldo de capital), un supuesto razonable inspirado en la
# normativa colombiana de provisión de cartera, documentado explícitamente
# porque el enunciado no da los porcentajes exactos a usar.
PROVISION_PCT = {"AL_DIA": 0.01, "RANGO_1": 0.05, "RANGO_2": 0.20, "RANGO_3": 0.50, "DETERIORADO": 1.00}


def bucket_mora_expr(col):
    return (
        F.when(col == 0, F.lit("AL_DIA"))
         .when((col >= 1) & (col <= 30), F.lit("RANGO_1"))
         .when((col >= 31) & (col <= 60), F.lit("RANGO_2"))
         .when((col >= 61) & (col <= 90), F.lit("RANGO_3"))
         .otherwise(F.lit("DETERIORADO"))
    )


def build_dim_clientes(silver):
    df = silver["tb_clientes_core"]
    segmento_label = {"BASICO": "Básico", "ESTANDAR": "Estándar", "PREMIUM": "Premium", "ELITE": "Elite"}
    mapping = F.create_map([F.lit(x) for kv in segmento_label.items() for x in kv])
    return (
        df.withColumn("nombre_completo", F.concat_ws(" ", "nomb_cli", "apell_cli"))
          .withColumn("edad", F.floor(F.datediff(F.current_date(), "fec_nac") / 365.25))
          .withColumn("segmento_legible", mapping[F.col("cod_segmento")])
          .select("id_cli", "nombre_completo", "tip_doc", "num_doc_hash", "fec_nac", "edad",
                   "cod_segmento", "segmento_legible", "score_buro", "score_buro_imputado",
                   "ciudad_res", "depto_res", "estado_cli", "canal_adquis")
    )


def build_dim_productos(silver):
    df = silver["tb_productos_cat"]
    familia = (
        F.when(F.col("tip_prod").isin("CREDITO_CONSUMO", "CREDITO_ROTATIVO", "TARJETA_DIGITAL"), F.lit("CREDITO"))
         .when(F.col("tip_prod") == "CUENTA_AHORRO", F.lit("AHORRO"))
         .otherwise(F.lit("TRANSACCIONAL"))
    )
    tasa_mensual = F.pow(F.lit(1) + F.col("tasa_ea"), F.lit(1 / 12.0)) - 1
    return (
        df.withColumn("familia", familia)
          .withColumn("tasa_mensual_equiv", F.round(tasa_mensual, 6))
          .select("cod_prod", "desc_prod", "tip_prod", "familia", "tasa_ea", "tasa_mensual_equiv",
                   "plazo_max_meses", "cuota_min", "comision_admin", "estado_prod")
    )


def build_dim_geografia(silver):
    return silver["tb_sucursales_red"].select("ciudad", "depto").distinct()


def build_dim_canal(silver):
    """Corrección de un hallazgo de auditoría: tip_punto solo toma los
    valores SUCURSAL/CORRESPONSAL/CAJERO (ver data-generation/generate_data.py,
    gen_sucursales) — los tres son puntos de atención físicos. Los canales
    verdaderamente digitales (APP, WEB) no son "puntos" en TB_SUCURSALES_RED:
    se registran como valor de cod_canal directamente en TB_MOV_FINANCIEROS
    (ver fact_transacciones.cod_canal). Marcar CORRESPONSAL como "canal
    digital" era un error de interpretación — un corresponsal bancario es
    un punto de atención físico asistido (una tienda con datáfono), no un
    canal digital. Por eso es_canal_digital es False para las tres, con esta
    razón documentada explícitamente en vez de dejar un flag engañoso."""
    df = silver["tb_sucursales_red"]
    return (
        df.withColumn("es_canal_digital", F.lit(False))
          .select("cod_suc", "tip_punto", "es_canal_digital", "activo")
    )


def build_fact_transacciones(silver, dim_clientes):
    df = silver["tb_mov_financieros"]
    horario_habil = (F.hour("hra_mov") >= 8) & (F.hour("hra_mov") < 18)
    df = (
        # Valida FK contra dim_clientes: solo pasan transacciones de clientes que existen en la dimensión.
        df.join(dim_clientes.select("id_cli"), "id_cli", "left_semi")
          .withColumn("vr_mov_usd", F.round(F.col("vr_mov") / F.lit(USD_COP_RATE), 2))
          .withColumn("flag_horario_habil", horario_habil)
    )
    return df.select("id_mov", "id_cli", "cod_prod", "num_cuenta_hash", "fec_mov", "hra_mov",
                      "vr_mov", "vr_mov_usd", "tip_mov", "cod_canal", "cod_ciudad",
                      "cod_estado_mov", "flag_horario_habil", "ind_sospechoso")


def build_fact_cartera(silver):
    df = silver["tb_obligaciones"]
    bucket = bucket_mora_expr(F.col("dias_mora_act"))
    provision_map = F.create_map([F.lit(x) for kv in PROVISION_PCT.items() for x in kv])
    return (
        df.withColumn("bucket_mora", bucket)
          .withColumn("provision_pct", provision_map[F.col("bucket_mora")])
          .withColumn("provision_estimada", F.round(F.col("sdo_capital") * F.col("provision_pct"), 2))
          .select("id_oblig", "id_cli", "cod_prod", "vr_aprobado", "vr_desembolsado", "sdo_capital",
                  "vr_cuota", "fec_desembolso", "fec_venc", "dias_mora_act", "bucket_mora",
                  "calif_riesgo", "provision_pct", "provision_estimada")
    )


def build_fact_rentabilidad_cliente(silver):
    """Supuesto documentado: el esquema origen no genera movimientos con un
    tipo explícito 'INTERES' en tb_mov_financieros, así que el ingreso por
    intereses se estima como el saldo de capital vigente de cada obligación
    (sdo_capital) multiplicado por la tasa mensual equivalente de su
    producto asociado. Ver pipelines/gold/README.md."""
    ob = silver["tb_obligaciones"]
    prod = silver["tb_productos_cat"].withColumn("tasa_mensual", F.pow(F.lit(1) + F.col("tasa_ea"), F.lit(1 / 12.0)) - 1)

    interes = (
        ob.join(prod.select("cod_prod", "tasa_mensual"), "cod_prod")
          .withColumn("periodo", F.date_format("fec_desembolso", "yyyy-MM"))
          .withColumn("ingreso_interes", F.round(F.col("sdo_capital") * F.col("tasa_mensual"), 2))
          .groupBy("id_cli", "periodo").agg(F.sum("ingreso_interes").alias("ingreso_interes"))
    )
    comisiones = (
        silver["tb_comisiones_log"]
        .filter(F.col("estado_cobro") == "COBRADA")
        .withColumn("periodo", F.date_format("fec_cobro", "yyyy-MM"))
        .groupBy("id_cli", "periodo").agg(F.sum("vr_comision").alias("ingreso_comisiones"))
    )
    rentab = (
        interes.join(comisiones, ["id_cli", "periodo"], "outer")
        .fillna(0, subset=["ingreso_interes", "ingreso_comisiones"])
        .withColumn("ingreso_total", F.col("ingreso_interes") + F.col("ingreso_comisiones"))
    )
    # CLTV = suma histórica de ingreso_total de los últimos 12 periodos mensuales por cliente.
    w = Window.partitionBy("id_cli").orderBy("periodo").rowsBetween(-11, 0)
    return rentab.withColumn("cltv_12m", F.round(F.sum("ingreso_total").over(w), 2))


def build_fact_kpis_cartera(fact_cartera, dim_clientes):
    df = fact_cartera.join(dim_clientes.select("id_cli", "cod_segmento", "ciudad_res"), "id_cli")
    kpis = (
        df.withColumn("fecha", F.current_date())
          .groupBy("fecha", "cod_prod", "cod_segmento", "ciudad_res")
          .agg(
              F.count("id_oblig").alias("total_obligaciones_activas"),
              F.round(F.sum("sdo_capital"), 2).alias("monto_total_cartera"),
              F.round(F.sum(F.when(F.col("bucket_mora") != "AL_DIA", F.col("sdo_capital")).otherwise(0)), 2).alias("monto_en_mora"),
              F.countDistinct(F.when(F.col("bucket_mora") != "AL_DIA", F.col("id_cli"))).alias("clientes_en_mora"),
          )
    )
    return kpis.withColumn(
        "tasa_mora_pct",
        F.when(F.col("monto_total_cartera") > 0, F.round(F.col("monto_en_mora") / F.col("monto_total_cartera") * 100, 2)).otherwise(0.0),
    )


def main():
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_bucket", "gold_bucket"])
    batch_id = str(uuid.uuid4())

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    silver_bucket, gold_bucket = args["silver_bucket"], args["gold_bucket"]
    silver = {t: spark.read.parquet(f"s3://{silver_bucket}/{t}/") for t in TABLES}

    dim_clientes = build_dim_clientes(silver)
    fact_cartera = build_fact_cartera(silver)

    outputs = {
        "dim_clientes": dim_clientes,
        "dim_productos": build_dim_productos(silver),
        "dim_geografia": build_dim_geografia(silver),
        "dim_canal": build_dim_canal(silver),
        "fact_transacciones": build_fact_transacciones(silver, dim_clientes),
        "fact_cartera": fact_cartera,
        "fact_rentabilidad_cliente": build_fact_rentabilidad_cliente(silver),
        "fact_kpis_cartera": build_fact_kpis_cartera(fact_cartera, dim_clientes),
    }

    for name, df in outputs.items():
        start = time.time()

        # Particionamiento por las dimensiones de análisis más frecuentes,
        # exigido por el enunciado para optimizar consultas sobre Gold.
        partition_cols = []
        if name == "fact_transacciones":
            df = df.withColumn("anio", F.year("fec_mov")).withColumn("mes", F.month("fec_mov"))
            partition_cols = ["anio", "mes"]
        elif name == "fact_cartera":
            df = df.withColumn("bucket_particion", F.col("bucket_mora"))
            partition_cols = ["bucket_particion"]

        n = df.count()
        writer = df.write.mode("overwrite")
        if partition_cols:
            writer = writer.partitionBy(*partition_cols)
        writer.parquet(f"s3://{gold_bucket}/{name}/")

        write_run_log(gold_bucket, "gold", name, batch_id, "SUCCESS", n, time.time() - start)
        print(f"[gold] {name}: {n} filas escritas")

    job.commit()


if __name__ == "__main__":
    main()
