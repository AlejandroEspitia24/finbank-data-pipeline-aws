"""Configuración de las 6 tablas origen de FinBank, compartida entre las
capas Bronze y Silver. Evita mantener la misma información duplicada en dos
scripts distintos.
"""

TABLES = {
    "tb_productos_cat":   {"mode": "full", "watermark_col": None, "pk": "cod_prod",
                            "required": ["cod_prod", "tip_prod"]},
    "tb_sucursales_red":  {"mode": "full", "watermark_col": None, "pk": "cod_suc",
                            "required": ["cod_suc"]},
    "tb_clientes_core":   {"mode": "full", "watermark_col": None, "pk": "id_cli",
                            "required": ["id_cli", "num_doc", "fec_nac"]},
    "tb_mov_financieros": {"mode": "incremental", "watermark_col": "fec_mov", "pk": "id_mov",
                            "required": ["id_mov", "id_cli", "cod_prod", "vr_mov", "fec_mov"],
                            "fk": {"id_cli": "tb_clientes_core", "cod_prod": "tb_productos_cat"}},
    "tb_obligaciones":    {"mode": "incremental", "watermark_col": "fec_desembolso", "pk": "id_oblig",
                            "required": ["id_oblig", "id_cli", "cod_prod"],
                            "fk": {"id_cli": "tb_clientes_core", "cod_prod": "tb_productos_cat"}},
    "tb_comisiones_log":  {"mode": "incremental", "watermark_col": "fec_cobro", "pk": "id_comision",
                            "required": ["id_comision", "id_cli", "cod_prod"],
                            "fk": {"id_cli": "tb_clientes_core", "cod_prod": "tb_productos_cat"}},
}
