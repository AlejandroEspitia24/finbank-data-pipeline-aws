# Diagrama Entidad-Relación — Fuente FinBank (sistema transaccional legado)

Este diagrama representa el esquema **origen** (RDS PostgreSQL), tal como se
definió en `data-generation/schema.sql`. Es el punto de partida que la capa
Bronze del pipeline ingiere sin transformaciones.

```mermaid
erDiagram
    TB_CLIENTES_CORE ||--o{ TB_MOV_FINANCIEROS : "realiza"
    TB_CLIENTES_CORE ||--o{ TB_OBLIGACIONES : "adquiere"
    TB_CLIENTES_CORE ||--o{ TB_COMISIONES_LOG : "genera"
    TB_PRODUCTOS_CAT ||--o{ TB_MOV_FINANCIEROS : "aplica_a"
    TB_PRODUCTOS_CAT ||--o{ TB_OBLIGACIONES : "aplica_a"
    TB_PRODUCTOS_CAT ||--o{ TB_COMISIONES_LOG : "aplica_a"

    TB_CLIENTES_CORE {
        bigint id_cli PK
        varchar nomb_cli
        varchar apell_cli
        varchar tip_doc
        varchar num_doc
        date fec_nac
        date fec_alta
        varchar cod_segmento
        int score_buro
        varchar ciudad_res
        varchar depto_res
        varchar estado_cli
        varchar canal_adquis
    }

    TB_PRODUCTOS_CAT {
        varchar cod_prod PK
        varchar desc_prod
        varchar tip_prod
        numeric tasa_ea
        int plazo_max_meses
        numeric cuota_min
        numeric comision_admin
        varchar estado_prod
    }

    TB_MOV_FINANCIEROS {
        bigint id_mov "sin PK: permite duplicados intencionales"
        bigint id_cli FK
        varchar cod_prod FK
        varchar num_cuenta
        date fec_mov
        time hra_mov
        numeric vr_mov
        varchar tip_mov
        varchar cod_canal
        varchar cod_ciudad
        varchar cod_estado_mov
        varchar id_dispositivo
    }

    TB_OBLIGACIONES {
        bigint id_oblig PK
        bigint id_cli FK
        varchar cod_prod FK
        numeric vr_aprobado
        numeric vr_desembolsado
        numeric sdo_capital
        numeric vr_cuota
        date fec_desembolso
        date fec_venc
        int dias_mora_act
        int num_cuotas_pend
        varchar calif_riesgo
    }

    TB_COMISIONES_LOG {
        bigint id_comision PK
        bigint id_cli FK
        varchar cod_prod FK
        date fec_cobro
        numeric vr_comision
        varchar tip_comision
        varchar estado_cobro
    }

    TB_SUCURSALES_RED {
        varchar cod_suc PK
        varchar nom_suc
        varchar tip_punto
        varchar ciudad
        varchar depto
        numeric latitud
        numeric longitud
        boolean activo
    }
```

> Nota: `TB_SUCURSALES_RED` no tiene una FK directa en el esquema origen (no
> existe columna que vincule sucursal con cliente/movimiento en las tablas
> fuente definidas por el enunciado). La relación con `dim_canal` /
> `dim_geografia` se construye en la capa Gold a partir de `cod_ciudad` como
> atributo descriptivo, no como llave.
