# API de Pasajes de Buses Interurbanos — EVA-2 Desarrollo Backend (Proyecto 4)

Backend en **Django REST Framework + PostgreSQL** para la venta de pasajes de buses interurbanos:
búsqueda de servicios, carro de pasajes persistente, checkout con verificación atómica de asientos,
emisión de boletos con UUID y gestión de estados por parte del Administrador de Flota.

## Tecnologías
- Django 6 + Django REST Framework
- PostgreSQL (motor `django.db.backends.postgresql`, driver psycopg 3)
- JWT con `djangorestframework-simplejwt` (access + refresh + blacklist)
- `django-filter` para filtros
- `drf-spectacular` para Swagger / OpenAPI

## Instalación

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Crear la base de datos en PostgreSQL
psql -U postgres -c "CREATE DATABASE buses_interurbanos_db;"

# (Opcional) credenciales distintas a postgres/postgres
$env:DB_PASSWORD = "mi_clave"

python manage.py migrate
python manage.py poblar_datos     # datos de demostración
python manage.py runserver
```

Variables de entorno soportadas: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`,
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `ALUMNO_NOMBRE`, `ALUMNO_SECCION`, `ALUMNO_ANIO`.

### Usuarios de prueba (`poblar_datos`)
| Usuario | Contraseña | Rol |
|---|---|---|
| admin_flota | Admin12345! | ADMIN_FLOTA (también superusuario de /admin/) |
| pasajero1 | Pasajero123! | PASAJERO |
| pasajero2 | Pasajero123! | PASAJERO |

## URLs principales
| URL | Descripción |
|---|---|
| `/` | Página base con matriz de endpoints y footer del alumno |
| `/api/docs/` | Swagger UI |
| `/api/redoc/` | ReDoc |
| `/api/schema/` | Esquema OpenAPI 3 |
| `/panel/` | **CRUD web con formularios** del Administrador de Flota (login en `/panel/login/`) |
| `/admin/` | Panel de administración de Django |

## CRUD web (panel del Administrador de Flota)

Vistas basadas en clases (`ListView`, `CreateView`, `UpdateView`, `DeleteView`, `DetailView`) con
`ModelForm`, en la app [panel/](panel/). Solo acceden usuarios con rol `ADMIN_FLOTA`
(sin sesión → redirige al login; pasajero → 403).

| Entidad | Listar | Crear | Editar | Eliminar | Extra |
|---|---|---|---|---|---|
| Ciudades | ✓ | ✓ | ✓ | ✓ | — |
| Terminales | ✓ | ✓ | ✓ | ✓ | — |
| Rutas | ✓ | ✓ | ✓ | ✓ | valida origen ≠ destino |
| Buses | ✓ | ✓ | ✓ | ✓ | — |
| Servicios | ✓ (filtros django-filter) | ✓ (genera asientos) | ✓ | ✓ | mapa de asientos |
| Ventas | ✓ (filtros) | — | — | — | detalle + cambio de estado (repone stock al cancelar) |

Si un registro tiene dependencias (FK `PROTECT`), el panel no lo elimina y muestra un mensaje.
El mismo CRUD está disponible por API REST en `/api/ciudades/`, `/api/terminales/`, `/api/rutas/`,
`/api/buses/` y `/api/servicios/`.

## Matriz de roles y permisos

| Rol | Endpoint | Permiso DRF |
|---|---|---|
| Público | `GET /api/servicios/buscar/?origen=&destino=` | `AllowAny` |
| Público | `GET /api/servicios/{id}/asientos/` | `AllowAny` |
| Público | `GET /api/servicios/`, `/api/ciudades/`, `/api/terminales/`, `/api/rutas/` | `LecturaPublicaEscrituraAdmin` |
| Pasajero | `GET/POST/DELETE /api/carro-pasajes/`, `PATCH/DELETE /api/carro-pasajes/{item_id}/` | `IsAuthenticated` + `EsPasajero` |
| Pasajero | `POST /api/ventas/checkout/`, `POST /api/ventas/{id}/pagar/` | `IsAuthenticated` + `EsPasajero` |
| Pasajero | `GET /api/mis-boletos/`, `GET /api/mis-ventas/` | `IsAuthenticated` + `EsPasajero` |
| Admin Flota | `POST/PUT/PATCH/DELETE /api/servicios/` (y ciudades, terminales, rutas), CRUD `/api/buses/` | `EsAdministradorFlota` |
| Admin Flota | `GET /api/ventas/`, `PATCH /api/ventas/{id}/estado/` | `EsAdministradorFlota` |

Los permisos personalizados están en [usuarios/permissions.py](usuarios/permissions.py) y leen el
claim `rol` directamente desde el token (`request.auth['rol']`).

## Flujo de uso (ejemplo)

1. **Login**: `POST /api/auth/login/` `{"username": "pasajero1", "password": "Pasajero123!"}`
   → `access`, `refresh` y `usuario.rol`. El payload del access incluye `rol`, `username`, `email`.
2. **Buscar**: `GET /api/servicios/buscar/?origen=santiago&destino=valparaiso&fecha=2026-10-01`
3. **Ver asientos**: `GET /api/servicios/1/asientos/?estado=DISPONIBLE&tipo=CAMA`
4. **Agregar al carro** (header `Authorization: Bearer <access>`):
   `POST /api/carro-pasajes/` `{"asiento": 5, "nombre_pasajero": "Juan Pérez", "tipo_documento": "RUT", "documento_pasajero": "11.111.111-1"}`
5. **Logout** (`POST /api/auth/logout/` con el refresh) y login nuevamente → `GET /api/carro-pasajes/` conserva los ítems.
6. **Checkout**: `POST /api/ventas/checkout/` `{"pagar": true}` → venta `PAGADO`, asientos `OCUPADO`, boletos con UUID.
7. **Mis boletos**: `GET /api/mis-boletos/`
8. **Admin cancela**: `PATCH /api/ventas/{id}/estado/` `{"estado": "CANCELADO", "observacion": "..."}` → asientos vuelven a `DISPONIBLE`.

## Modelo de datos

```
Usuario (rol CHOICES) 1──1 Carro 1──N ItemCarro N──1 Asiento
Usuario 1──N Venta (estado CHOICES) 1──N DetalleVenta (precio congelado) 1──1 Boleto (UUID)
Ciudad 1──N Terminal 1──N Ruta (origen/destino) 1──N Servicio N──1 Bus
Servicio (estado CHOICES) 1──N Asiento (tipo CHOICES, estado CHOICES)
```

## Ciclo de la transacción y stock

- **Stock** = asientos de cada servicio (`DISPONIBLE` / `OCUPADO`). Se generan por señal al crear
  el servicio según la distribución del bus ([flota/signals.py](flota/signals.py)).
- **Agregar al carro no descuenta** nada.
- **Checkout** ([ventas/services.py](ventas/services.py)): dentro de `transaction.atomic()`, bloquea
  los asientos con `SELECT ... FOR UPDATE`, verifica que ninguno esté ocupado, crea la `Venta`
  `PENDIENTE` con los precios congelados en `DetalleVenta` y vacía el carro.
- **Pago (`PAGADO`)**: vuelve a bloquear y verificar; si algún asiento ya fue vendido responde
  **409** y hace ROLLBACK. Si todo está bien, marca los asientos `OCUPADO` y emite un `Boleto` por asiento.
- **Cancelación**: si la venta estaba pagada y el bus no ha salido, los asientos vuelven a
  `DISPONIBLE` y los boletos quedan `ANULADO`.
- Transiciones: `PENDIENTE → PAGADO → COMPLETADO` y `PENDIENTE/PAGADO → CANCELADO`.

## Filtros (django-filter)
- `/api/servicios/`: `origen`, `destino`, `fecha`, `fecha_desde`, `fecha_hasta`, `tarifa_min`,
  `tarifa_max`, `estado`, `tipo_asiento`, `con_disponibilidad`, `ruta`, `bus`, más `search` y `ordering`.
- `/api/servicios/{id}/asientos/`: `tipo`, `estado`.
- `/api/rutas/`: `origen`, `destino`, `distancia_max`.
- `/api/ventas/` y `/api/mis-ventas/`: `estado`, `creada_desde`, `creada_hasta`, `total_min`, `total_max`, `usuario`.
- `/api/mis-boletos/`: `estado`, `servicio`, `origen`, `destino`, `fecha_viaje`.

## Pruebas

```powershell
python manage.py test
```
Cubren: claim de rol en el JWT, permisos por rol, filtros, persistencia del carro tras logout,
validación de RUT, checkout con descuento de stock, precio congelado, rechazo por asiento ya
vendido, cancelación con reposición de stock y aislamiento de ventas entre usuarios.

---
**Alumno:** Jonathan Nicolas Verdugo Garrido — **Sección:** IEC-N4-C1 — **Año:** 2026
