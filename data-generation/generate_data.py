"""Generador de datos sintéticos para el escenario FinBank (Prueba Técnica DataKnow).

Genera las 6 tablas del sistema transaccional legado con distribuciones
realistas, integridad referencial garantizada y anomalías intencionales
documentadas. Reproducible vía semilla fija en config.yaml.

Uso:
    python generate_data.py --config config.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from faker import Faker

from logging_config import setup_logging

logger = logging.getLogger(__name__)

CITIES: list[tuple[str, str]] = [
    ("Bogotá", "Cundinamarca"),
    ("Medellín", "Antioquia"),
    ("Cali", "Valle del Cauca"),
    ("Barranquilla", "Atlántico"),
    ("Ciudad de México", "CDMX"),
    ("Guadalajara", "Jalisco"),
    ("Monterrey", "Nuevo León"),
    ("Lima", "Lima"),
    ("Arequipa", "Arequipa"),
    ("Santiago", "Región Metropolitana"),
    ("Valparaíso", "Valparaíso"),
    ("Buenos Aires", "Buenos Aires"),
    ("Córdoba", "Córdoba"),
]

# Pesos por hora del día para concentrar transacciones en horario "hábil",
# tal como pide el enunciado ("las ventas deben concentrarse en horarios pico").
HOUR_WEIGHTS = np.array([
    0.2, 0.1, 0.1, 0.1, 0.2, 0.5, 1.0, 2.0,   # 0-7h
    4.0, 5.0, 5.5, 5.5, 5.0, 5.0, 5.0, 5.0,   # 8-15h
    5.5, 5.5, 5.0, 4.0, 3.0, 2.0, 1.0, 0.5,   # 16-23h
])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def random_dates(rng: np.random.Generator, start: pd.Timestamp, end: pd.Timestamp, size: int) -> np.ndarray:
    span_days = (end - start).days
    offsets = rng.integers(0, span_days + 1, size=size)
    return np.array([start + pd.Timedelta(days=int(d)) for d in offsets])


def inject_nulls(df: pd.DataFrame, columns: list[str], rate: float, rng: np.random.Generator) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        mask = rng.random(len(df)) < rate
        df.loc[mask, col] = None
    return df


# --------------------------------------------------------------------------- #
# Tablas dimensión (sin dependencias de FK)
# --------------------------------------------------------------------------- #

def gen_productos(n: int, rng: np.random.Generator) -> pd.DataFrame:
    familias = rng.choice(
        ["CREDITO_CONSUMO", "CREDITO_ROTATIVO", "TARJETA_DIGITAL", "CUENTA_AHORRO", "TRANSACCIONAL"],
        size=n,
        p=[0.25, 0.15, 0.15, 0.25, 0.20],
    )
    tasa_ea = np.where(
        np.isin(familias, ["CREDITO_CONSUMO", "CREDITO_ROTATIVO", "TARJETA_DIGITAL"]),
        np.round(rng.uniform(0.18, 0.45, n), 4),
        np.round(rng.uniform(0.0, 0.03, n), 4),
    )
    plazo = np.where(
        familias == "CREDITO_CONSUMO", rng.choice([12, 24, 36, 48, 60], n),
        np.where(familias == "CREDITO_ROTATIVO", rng.choice([0, 3, 6], n), 0),
    )
    return pd.DataFrame({
        "cod_prod": [f"PRD{i:04d}" for i in range(1, n + 1)],
        "desc_prod": [f"{f.replace('_', ' ').title()} {i}" for i, f in enumerate(familias, 1)],
        "tip_prod": familias,
        "tasa_ea": tasa_ea,
        "plazo_max_meses": plazo,
        "cuota_min": np.round(rng.uniform(30000, 300000, n), 2),
        "comision_admin": np.round(rng.uniform(0, 25000, n), 2),
        "estado_prod": rng.choice(["ACTIVO", "INACTIVO"], n, p=[0.92, 0.08]),
    })


def gen_sucursales(n: int, rng: np.random.Generator) -> pd.DataFrame:
    idx = rng.integers(0, len(CITIES), n)
    ciudades = [CITIES[i][0] for i in idx]
    deptos = [CITIES[i][1] for i in idx]
    tipos = rng.choice(["SUCURSAL", "CORRESPONSAL", "CAJERO"], n, p=[0.25, 0.55, 0.20])
    return pd.DataFrame({
        "cod_suc": [f"SUC{i:04d}" for i in range(1, n + 1)],
        "nom_suc": [f"{t.title()} {c} {i}" for i, (t, c) in enumerate(zip(tipos, ciudades), 1)],
        "tip_punto": tipos,
        "ciudad": ciudades,
        "depto": deptos,
        "latitud": np.round(rng.uniform(-33.0, 12.0, n), 6),
        "longitud": np.round(rng.uniform(-99.0, -58.0, n), 6),
        "activo": rng.choice([True, False], n, p=[0.95, 0.05]),
    })


def gen_clientes(n: int, reference_date: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    fake = Faker("es_CO")
    # seed_instance() semilla SOLO esta instancia de Faker (no el estado
    # global del módulo), consistente con el mismo principio que aplicamos
    # a numpy: nada de estado aleatorio compartido/oculto entre funciones.
    fake.seed_instance(int(rng.integers(0, 2**31 - 1)))

    # Edad ~normal (media 38, desv 12), acotada entre 18 y 80 años, tal como
    # pide el enunciado ("las edades deben seguir una distribución normal").
    edades = np.clip(rng.normal(38, 12, n), 18, 80).astype(int)
    fec_nac = [reference_date - pd.DateOffset(years=int(e), days=int(rng.integers(0, 365))) for e in edades]

    # La fecha de alta no puede ser antes de que el cliente cumpla 18 años.
    fec_alta = []
    for nac in fec_nac:
        alta_min = max(nac + pd.DateOffset(years=18), reference_date - pd.DateOffset(years=8))
        span = max((reference_date - alta_min).days, 1)
        fec_alta.append(alta_min + pd.Timedelta(days=int(rng.integers(0, span))))

    idx = rng.integers(0, len(CITIES), n)
    ciudades = [CITIES[i][0] for i in idx]
    deptos = [CITIES[i][1] for i in idx]

    return pd.DataFrame({
        "id_cli": np.arange(1, n + 1),
        "nomb_cli": [fake.first_name() for _ in range(n)],
        "apell_cli": [fake.last_name() for _ in range(n)],
        "tip_doc": rng.choice(["CC", "CE", "PA"], n, p=[0.90, 0.07, 0.03]),
        "num_doc": [fake.unique.numerify("##########") for _ in range(n)],
        "fec_nac": fec_nac,
        "fec_alta": fec_alta,
        "cod_segmento": rng.choice(
            ["BASICO", "ESTANDAR", "PREMIUM", "ELITE"], n, p=[0.35, 0.40, 0.20, 0.05]
        ),
        "score_buro": np.clip(rng.normal(650, 120, n), 150, 950).astype(int),
        "ciudad_res": ciudades,
        "depto_res": deptos,
        "estado_cli": rng.choice(["ACTIVO", "INACTIVO", "BLOQUEADO"], n, p=[0.90, 0.07, 0.03]),
        "canal_adquis": rng.choice(["APP", "WEB", "CORRESPONSAL"], n, p=[0.55, 0.30, 0.15]),
    })


# --------------------------------------------------------------------------- #
# Tablas de hechos (dependen de clientes / productos ya generados)
# --------------------------------------------------------------------------- #

def gen_movimientos(n: int, clientes: pd.DataFrame, productos: pd.DataFrame,
                     start: pd.Timestamp, end: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    cliente_ids = clientes["id_cli"].values
    prod_ids = productos["cod_prod"].values

    tip_mov = rng.choice(
        ["COMPRA", "PAGO", "TRANSFERENCIA", "AVANCE", "RECARGA"], n, p=[0.35, 0.30, 0.20, 0.05, 0.10]
    )
    # Cada tipo de movimiento tiene un orden de magnitud distinto de monto,
    # tal como exige el enunciado ("los montos deben reflejar comportamientos
    # típicos del sector").
    base_mu = np.select(
        [tip_mov == "COMPRA", tip_mov == "PAGO", tip_mov == "TRANSFERENCIA",
         tip_mov == "AVANCE", tip_mov == "RECARGA"],
        [11.5, 12.5, 13.0, 13.5, 9.5],
    )
    vr_mov = np.round(rng.lognormal(base_mu, 0.6, n), 2)

    hours = rng.choice(24, size=n, p=HOUR_WEIGHTS)
    minutes = rng.integers(0, 60, n)
    seconds = rng.integers(0, 60, n)
    hra_mov = [f"{h:02d}:{m:02d}:{s:02d}" for h, m, s in zip(hours, minutes, seconds)]

    fec_mov = random_dates(rng, start, end, n)

    idx = rng.integers(0, len(CITIES), n)
    ciudades = [CITIES[i][0] for i in idx]

    return pd.DataFrame({
        "id_mov": np.arange(1, n + 1),
        "id_cli": rng.choice(cliente_ids, n),
        "cod_prod": rng.choice(prod_ids, n),
        "num_cuenta": [f"CTA{v:010d}" for v in rng.integers(1, 99_999_999, n)],
        "fec_mov": fec_mov,
        "hra_mov": hra_mov,
        "vr_mov": vr_mov,
        "tip_mov": tip_mov,
        "cod_canal": rng.choice(["APP", "WEB", "CORRESPONSAL", "ATM"], n, p=[0.60, 0.20, 0.12, 0.08]),
        "cod_ciudad": ciudades,
        "cod_estado_mov": rng.choice(["EXITOSA", "RECHAZADA", "PENDIENTE"], n, p=[0.92, 0.05, 0.03]),
        "id_dispositivo": [f"DEV{v:08d}" for v in rng.integers(1, 999_999, n)],
    })


def gen_obligaciones(n: int, clientes: pd.DataFrame, productos: pd.DataFrame,
                      start: pd.Timestamp, end: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    credit_products = productos[productos["tip_prod"].isin(
        ["CREDITO_CONSUMO", "CREDITO_ROTATIVO", "TARJETA_DIGITAL"]
    )]
    cliente_ids = clientes["id_cli"].values
    prod_ids = credit_products["cod_prod"].values

    vr_aprobado = np.round(rng.lognormal(15.0, 0.6, n), 2)
    vr_desembolsado = np.round(vr_aprobado * rng.uniform(0.7, 1.0, n), 2)

    fec_desembolso = random_dates(rng, start, end, n)
    plazos_meses = rng.choice([12, 24, 36, 48, 60], n)
    fec_venc = [d + pd.DateOffset(months=int(p)) for d, p in zip(fec_desembolso, plazos_meses)]

    # Distribución de mora: mayoría al día, cola larga hacia deteriorado —
    # así el KPI de cartera (fact_kpis_cartera) tendrá variación real que
    # analizar, no solo ceros.
    bucket = rng.choice([0, 1, 2, 3, 4], n, p=[0.70, 0.15, 0.08, 0.04, 0.03])
    dias_mora_act = np.select(
        [bucket == 0, bucket == 1, bucket == 2, bucket == 3, bucket == 4],
        [
            np.zeros(n),
            rng.integers(1, 31, n),
            rng.integers(31, 61, n),
            rng.integers(61, 91, n),
            rng.integers(91, 400, n),
        ],
    )
    calif_riesgo = np.select(
        [bucket == 0, bucket == 1, bucket == 2, bucket == 3, bucket == 4],
        [
            rng.choice(["A", "B"], n, p=[0.8, 0.2]),
            rng.choice(["B", "C"], n, p=[0.6, 0.4]),
            rng.choice(["C", "D"], n, p=[0.5, 0.5]),
            np.full(n, "D"),
            np.full(n, "E"),
        ],
        # default explícito y del mismo tipo (str) que el choicelist: numpy
        # 2.x ya no infiere un dtype común entre int (default implícito 0) y
        # str, y lanza TypeError. Las 5 condiciones cubren todos los buckets
        # posibles, así que este valor nunca se usa en la práctica.
        default="A",
    )

    sdo_capital = np.round(vr_desembolsado * rng.uniform(0.2, 0.95, n), 2)
    vr_cuota = np.round(vr_desembolsado / plazos_meses.clip(min=1) * rng.uniform(1.02, 1.15, n), 2)
    num_cuotas_pend = np.round(sdo_capital / vr_cuota.clip(min=1)).astype(int)

    return pd.DataFrame({
        "id_oblig": np.arange(1, n + 1),
        "id_cli": rng.choice(cliente_ids, n),
        "cod_prod": rng.choice(prod_ids, n),
        "vr_aprobado": vr_aprobado,
        "vr_desembolsado": vr_desembolsado,
        "sdo_capital": sdo_capital,
        "vr_cuota": vr_cuota,
        "fec_desembolso": fec_desembolso,
        "fec_venc": fec_venc,
        "dias_mora_act": dias_mora_act.astype(int),
        "num_cuotas_pend": num_cuotas_pend,
        "calif_riesgo": calif_riesgo,
    })


def gen_comisiones(n: int, clientes: pd.DataFrame, productos: pd.DataFrame,
                    start: pd.Timestamp, end: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    cliente_ids = clientes["id_cli"].values
    prod_ids = productos["cod_prod"].values
    return pd.DataFrame({
        "id_comision": np.arange(1, n + 1),
        "id_cli": rng.choice(cliente_ids, n),
        "cod_prod": rng.choice(prod_ids, n),
        "fec_cobro": random_dates(rng, start, end, n),
        "vr_comision": np.round(rng.lognormal(9.5, 0.7, n), 2),
        "tip_comision": rng.choice(["ADMIN", "MANEJO", "AVANCE"], n, p=[0.50, 0.35, 0.15]),
        "estado_cobro": rng.choice(["COBRADA", "PENDIENTE", "REVERSADA"], n, p=[0.90, 0.07, 0.03]),
    })


# --------------------------------------------------------------------------- #
# Anomalías intencionales (documentadas — ver docs/PLAN.md)
# --------------------------------------------------------------------------- #

def inject_anomalies(mov: pd.DataFrame, obligaciones: pd.DataFrame, cfg: dict,
                      start: pd.Timestamp, end: pd.Timestamp, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    mov = mov.copy()
    obligaciones = obligaciones.copy()

    # Anomalía 1: transacciones duplicadas exactas (simula reintento de ingesta).
    dup_rate = cfg["anomalies"]["duplicate_movimientos_rate"]
    n_dup = int(len(mov) * dup_rate)
    dup_rows = mov.sample(n=n_dup, random_state=rng)
    mov = pd.concat([mov, dup_rows], ignore_index=True)
    logger.info("Anomalía 1/3: %d transacciones duplicadas inyectadas en TB_MOV_FINANCIEROS", n_dup)

    # Anomalía 2: fechas de movimiento fuera del rango histórico esperado.
    oor_rate = cfg["anomalies"]["out_of_range_dates_rate"]
    oor_mask = rng.random(len(mov)) < oor_rate
    n_oor = int(oor_mask.sum())
    bad_dates = np.where(
        rng.random(n_oor) < 0.5,
        [end + pd.Timedelta(days=int(d)) for d in rng.integers(1, 90, n_oor)],       # futuras
        [start - pd.Timedelta(days=int(d)) for d in rng.integers(1, 400, n_oor)],    # muy anteriores
    )
    mov.loc[oor_mask, "fec_mov"] = bad_dates
    logger.info("Anomalía 2/3: %d fechas fuera de rango inyectadas en TB_MOV_FINANCIEROS", n_oor)

    # Anomalía 3: obligaciones con vr_desembolsado > vr_aprobado (inconsistencia
    # de negocio que Silver debe rechazar o marcar en la tabla de errores).
    inc_rate = cfg["anomalies"]["inconsistent_obligaciones_rate"]
    inc_mask = rng.random(len(obligaciones)) < inc_rate
    n_inc = int(inc_mask.sum())
    obligaciones.loc[inc_mask, "vr_desembolsado"] = (
        obligaciones.loc[inc_mask, "vr_aprobado"] * rng.uniform(1.05, 1.30, n_inc)
    ).round(2)
    logger.info("Anomalía 3/3: %d obligaciones con vr_desembolsado > vr_aprobado inyectadas", n_inc)

    return mov, obligaciones


# --------------------------------------------------------------------------- #
# Salida
# --------------------------------------------------------------------------- #

def save_outputs(tables: dict[str, pd.DataFrame], formats: list[str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        if "csv" in formats:
            df.to_csv(out_dir / f"{name}.csv", index=False)
        if "parquet" in formats:
            df.to_parquet(out_dir / f"{name}.parquet", index=False)
        logger.info("  %-20s %10s filas", name, f"{len(df):,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    out_dir = Path(cfg["output"]["dir"])
    setup_logging(out_dir / "generation.log")

    try:
        seed = cfg["seed"]
        rng = np.random.default_rng(seed)

        reference_date = pd.Timestamp(cfg["reference_date"])
        start = reference_date - pd.DateOffset(months=cfg["history_months"])
        end = reference_date
        v = cfg["volumes"]

        logger.info("Iniciando generación | semilla=%s | rango histórico=%s a %s", seed, start.date(), end.date())

        logger.info("Generando tablas dimensión (productos, sucursales, clientes)...")
        productos = gen_productos(v["productos"], rng)
        sucursales = gen_sucursales(v["sucursales"], rng)
        clientes = gen_clientes(v["clientes"], reference_date, rng)

        logger.info("Generando tablas de hechos (movimientos, obligaciones, comisiones)...")
        movimientos = gen_movimientos(v["movimientos"], clientes, productos, start, end, rng)
        obligaciones = gen_obligaciones(v["obligaciones"], clientes, productos, start, end, rng)
        comisiones = gen_comisiones(v["comisiones"], clientes, productos, start, end, rng)

        logger.info("Inyectando anomalías intencionales...")
        movimientos, obligaciones = inject_anomalies(movimientos, obligaciones, cfg, start, end, rng)

        logger.info("Inyectando ~%.0f%% de nulos en columnas no críticas...", cfg["null_rate"] * 100)
        clientes = inject_nulls(clientes, ["depto_res", "canal_adquis", "score_buro"], cfg["null_rate"], rng)
        movimientos = inject_nulls(movimientos, ["id_dispositivo", "cod_canal"], cfg["null_rate"], rng)
        obligaciones = inject_nulls(obligaciones, ["num_cuotas_pend"], cfg["null_rate"], rng)
        comisiones = inject_nulls(comisiones, ["tip_comision"], cfg["null_rate"], rng)

        tables = {
            "tb_productos_cat": productos,
            "tb_sucursales_red": sucursales,
            "tb_clientes_core": clientes,
            "tb_mov_financieros": movimientos,
            "tb_obligaciones": obligaciones,
            "tb_comisiones_log": comisiones,
        }

        logger.info("Guardando archivos de salida (%s)...", ", ".join(cfg["output"]["formats"]))
        save_outputs(tables, cfg["output"]["formats"], out_dir)
        logger.info("Generación completa. Archivos en: %s", out_dir.resolve())
        return 0

    except Exception:
        # logger.exception() incluye el traceback completo en el log, no solo
        # el mensaje — esencial para poder depurar una corrida fallida sin
        # tener que reproducir el error interactivamente.
        logger.exception("Fallo no controlado durante la generación de datos")
        return 1


if __name__ == "__main__":
    sys.exit(main())
