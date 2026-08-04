# Evidencia — Fase 5 / Gobierno, seguridad y calidad

## Recursos desplegados

| Recurso | Nombre / ARN |
|---|---|
| Rol Ingeniero de Datos | `arn:aws:iam::278714105600:role/finbank-dev-data-engineer-role` |
| Rol Analista | `arn:aws:iam::278714105600:role/finbank-dev-analyst-role` |
| Rol Administrador | `arn:aws:iam::278714105600:role/finbank-dev-administrator-role` |
| Trail de CloudTrail | `arn:aws:cloudtrail:us-east-1:278714105600:trail/finbank-dev-trail` |
| Bucket de logs de CloudTrail | `finbank-cloudtrail-dev-278714105600` |

Desplegado vía `terraform apply` (12 recursos nuevos, 0 modificados, 0
destruidos) contra la cuenta AWS real `278714105600`.

## Verificación real de aislamiento por rol (no solo "la política dice que...")

Se asumió el rol `finbank-dev-analyst-role` con `aws sts assume-role` y se
probó acceso real con las credenciales temporales resultantes:

```
$ aws sts get-caller-identity
arn:aws:sts::278714105600:assumed-role/finbank-dev-analyst-role/test-analyst

$ aws s3 ls s3://finbank-gold-dev-278714105600/
                           PRE dim_canal/
                           PRE dim_clientes/
                           PRE dim_geografia/
                           PRE dim_productos/
                           ...                          ✅ permitido

$ aws s3 ls s3://finbank-silver-dev-278714105600/
AccessDenied: User ... finbank-dev-analyst-role/test-analyst is not
authorized to perform: s3:ListBucket on resource:
"arn:aws:s3:::finbank-silver-dev-278714105600"                ❌ denegado (esperado)

$ aws s3 ls s3://finbank-bronze-dev-278714105600/
AccessDenied: User ... finbank-dev-analyst-role/test-analyst-bronze is not
authorized to perform: s3:ListBucket on resource:
"arn:aws:s3:::finbank-bronze-dev-278714105600"                ❌ denegado (esperado)
```

Confirma que el aislamiento de **ambas** capas restringidas (Silver y
Bronze) frente al rol Analista es real a nivel de API de AWS, no solo una
intención declarada en la política — el entregable explícito de la Fase 5
pide "demostración de que el perfil Analista no puede acceder a las capas
Bronze o Silver directamente", y ambas quedaron probadas, no solo una.

## CloudTrail — auditoría activa y verificada

```
$ aws cloudtrail get-trail-status --name finbank-dev-trail
{ "IsLogging": true, ... }

$ aws cloudtrail lookup-events --max-results 5
2026-08-03T20:03:29-05:00  finbank-terraform-deployer  GetBucketLifecycle
2026-08-03T20:03:24-05:00  finbank-terraform-deployer  GetBucketLifecycle
...

$ aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole
2026-08-03T19:55:04-05:00  AssumeRole
2026-08-03T19:50:36-05:00  AssumeRole
...
```

`IsLogging: true` confirma el trail activo. `lookup-events` (Event
History, siempre activo y gratuito, independiente de la entrega a S3)
confirma que los eventos de la cuenta —incluyendo los `AssumeRole` de la
prueba de aislamiento de arriba— quedan registrados y son consultables.
La entrega de logs al bucket S3 (`AWSLogs/278714105600/CloudTrail/...`)
puede tardar hasta ~15 minutos desde la creación del trail; no bloquea la
auditoría inmediata vía `lookup-events`.

## Corrección post-auditoría: auditoría a nivel de dato (data events de S3)

Una auditoría contra el enunciado detectó que el trail original solo
registraba *management events* — no podía responder "¿quién accedió a qué
dato y en qué momento?" (requisito explícito de la Fase 5), porque esa
pregunta requiere eventos de datos (data events) de S3, no solo eventos de
administración de recursos. Se agregó un `data_resource` de tipo
`AWS::S3::Object` acotado a los 3 buckets del Data Lake (no a toda la
cuenta, para controlar costo/volumen). Verificado:

```json
$ aws cloudtrail get-event-selectors --trail-name finbank-dev-trail
{
  "EventSelectors": [{
    "ReadWriteType": "All",
    "IncludeManagementEvents": true,
    "DataResources": [{
      "Type": "AWS::S3::Object",
      "Values": [
        "arn:aws:s3:::finbank-bronze-dev-278714105600/",
        "arn:aws:s3:::finbank-gold-dev-278714105600/",
        "arn:aws:s3:::finbank-silver-dev-278714105600/"
      ]
    }]
  }]
}
```

Con esto, cualquier `GetObject`/`PutObject` sobre las 3 capas queda
registrado con identidad del llamante, hora exacta y objeto accedido —
cerrando el gap real que existía entre "auditar la infraestructura" y
"auditar el dato", que son cosas distintas.

## Catálogo de datos

`docs/catalogo-datos.md`: inventario **campo por campo** de las 7 tablas
Silver + 8 tablas Gold — para cada columna: tipo, origen exacto (tabla
fuente o fórmula de cálculo), y nivel de sensibilidad (PII directa /
indirecta / no sensible), tal como lo exige el entregable de la Fase 5
("descripción de cada campo, su tipo, su origen y si contiene información
sensible"). Referenciado también desde el README de Gold para el linaje
exacto de cada campo calculado.

## Costo real incurrido (Fase 5)

- CloudTrail (management events, un solo trail, una sola región): sin
  costo — es la primera copia de eventos de administración por región,
  que AWS no cobra.
- Bucket S3 de logs de CloudTrail: costo de almacenamiento trivial
  (JSON pequeños), con expiración automática a los 90 días.
- Roles IAM: sin costo (IAM no cobra por roles ni políticas).
