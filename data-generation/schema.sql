-- Esquema relacional de origen de FinBank S.A.
-- Refleja la nomenclatura interna del sistema legado tal como la define
-- el enunciado de la prueba técnica (Escenario A — Banca).
--
-- Nota de diseño: id_mov en TB_MOV_FINANCIEROS NO tiene UNIQUE/PRIMARY KEY.
-- Es intencional: el generador de datos inyecta duplicados exactos para
-- simular un problema real de ingesta que la capa Silver del pipeline
-- debe detectar y resolver (ver docs/PLAN.md, sección de anomalías).

DROP TABLE IF EXISTS tb_comisiones_log CASCADE;
DROP TABLE IF EXISTS tb_obligaciones CASCADE;
DROP TABLE IF EXISTS tb_mov_financieros CASCADE;
DROP TABLE IF EXISTS tb_clientes_core CASCADE;
DROP TABLE IF EXISTS tb_sucursales_red CASCADE;
DROP TABLE IF EXISTS tb_productos_cat CASCADE;

CREATE TABLE tb_productos_cat (
    cod_prod        VARCHAR(10) PRIMARY KEY,
    desc_prod       VARCHAR(100) NOT NULL,
    tip_prod        VARCHAR(30) NOT NULL,
    tasa_ea         NUMERIC(6,4),
    plazo_max_meses INT,
    cuota_min       NUMERIC(14,2),
    comision_admin  NUMERIC(14,2),
    estado_prod     VARCHAR(20)
);

CREATE TABLE tb_sucursales_red (
    cod_suc   VARCHAR(10) PRIMARY KEY,
    nom_suc   VARCHAR(100),
    tip_punto VARCHAR(20),
    ciudad    VARCHAR(60),
    depto     VARCHAR(60),
    latitud   NUMERIC(9,6),
    longitud  NUMERIC(9,6),
    activo    BOOLEAN
);

CREATE TABLE tb_clientes_core (
    id_cli       BIGINT PRIMARY KEY,
    nomb_cli     VARCHAR(60),
    apell_cli    VARCHAR(60),
    tip_doc      VARCHAR(5),
    num_doc      VARCHAR(20),
    fec_nac      DATE,
    fec_alta     DATE,
    cod_segmento VARCHAR(20),
    score_buro   INT,
    ciudad_res   VARCHAR(60),
    depto_res    VARCHAR(60),
    estado_cli   VARCHAR(20),
    canal_adquis VARCHAR(20)
);

CREATE TABLE tb_mov_financieros (
    id_mov         BIGINT NOT NULL,
    id_cli         BIGINT REFERENCES tb_clientes_core(id_cli),
    cod_prod       VARCHAR(10) REFERENCES tb_productos_cat(cod_prod),
    num_cuenta     VARCHAR(20),
    fec_mov        DATE,
    hra_mov        TIME,
    vr_mov         NUMERIC(14,2),
    tip_mov        VARCHAR(20),
    cod_canal      VARCHAR(20),
    cod_ciudad     VARCHAR(60),
    cod_estado_mov VARCHAR(20),
    id_dispositivo VARCHAR(40)
);

CREATE TABLE tb_obligaciones (
    id_oblig        BIGINT PRIMARY KEY,
    id_cli          BIGINT REFERENCES tb_clientes_core(id_cli),
    cod_prod        VARCHAR(10) REFERENCES tb_productos_cat(cod_prod),
    vr_aprobado     NUMERIC(14,2),
    vr_desembolsado NUMERIC(14,2),
    sdo_capital     NUMERIC(14,2),
    vr_cuota        NUMERIC(14,2),
    fec_desembolso  DATE,
    fec_venc        DATE,
    dias_mora_act   INT,
    num_cuotas_pend INT,
    calif_riesgo    VARCHAR(2)
);

CREATE TABLE tb_comisiones_log (
    id_comision  BIGINT PRIMARY KEY,
    id_cli       BIGINT REFERENCES tb_clientes_core(id_cli),
    cod_prod     VARCHAR(10) REFERENCES tb_productos_cat(cod_prod),
    fec_cobro    DATE,
    vr_comision  NUMERIC(14,2),
    tip_comision VARCHAR(20),
    estado_cobro VARCHAR(20)
);

CREATE INDEX idx_mov_id_cli ON tb_mov_financieros(id_cli);
CREATE INDEX idx_mov_fec ON tb_mov_financieros(fec_mov);
CREATE INDEX idx_oblig_id_cli ON tb_obligaciones(id_cli);
CREATE INDEX idx_comision_id_cli ON tb_comisiones_log(id_cli);
