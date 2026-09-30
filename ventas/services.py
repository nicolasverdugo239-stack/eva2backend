"""
=====================================================================
LÓGICA DE NEGOCIO TRANSACCIONAL (CHECKOUT, PAGO, CANCELACIÓN)
=====================================================================
Toda modificación del "stock" (estado de los asientos) ocurre aquí,
dentro de transaction.atomic() y con bloqueo de filas
SELECT ... FOR UPDATE en PostgreSQL.

¿Por qué SELECT ... FOR UPDATE?
    Si dos pasajeros intentan pagar el MISMO asiento al mismo tiempo, el
    primero bloquea la fila del asiento; el segundo queda esperando hasta
    que el primero haga COMMIT. Al obtener el bloqueo, PostgreSQL le
    entrega la versión ya actualizada (OCUPADO) y su pago se rechaza.
    Así es imposible vender dos veces el mismo asiento.

¿Por qué transaction.atomic()?
    Si cualquier paso falla (lanza una excepción), PostgreSQL hace
    ROLLBACK de todo el bloque: no quedan asientos ocupados sin boleto,
    ni ventas a medio crear, ni carros vaciados sin venta.

Las excepciones heredan de APIException, por lo que DRF las transforma
automáticamente en respuestas HTTP (400 / 409) con el detalle del error.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from flota.models import Asiento

from .models import Boleto, Carro, DetalleVenta, Venta


# ---------------------------------------------------------------------
# BLOQUE: Excepciones de negocio
# ---------------------------------------------------------------------
class CarroVacio(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'El carro de pasajes está vacío.'
    default_code = 'carro_vacio'


class AsientosNoDisponibles(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Uno o más asientos ya no están disponibles. La transacción fue rechazada.'
    default_code = 'asientos_no_disponibles'


class TransicionInvalida(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Transición de estado no permitida.'
    default_code = 'transicion_invalida'


# ---------------------------------------------------------------------
# BLOQUE: Máquina de estados de la Venta
# Define qué cambios de estado son válidos desde cada estado actual.
# COMPLETADO y CANCELADO son estados finales.
# ---------------------------------------------------------------------
TRANSICIONES = {
    Venta.Estado.PENDIENTE: {Venta.Estado.PAGADO, Venta.Estado.CANCELADO},
    Venta.Estado.PAGADO: {Venta.Estado.COMPLETADO, Venta.Estado.CANCELADO},
    Venta.Estado.COMPLETADO: set(),
    Venta.Estado.CANCELADO: set(),
}


# ---------------------------------------------------------------------
# BLOQUE: Utilidades de bloqueo y verificación de asientos
# ---------------------------------------------------------------------
def _bloquear_asientos(asiento_ids):
    """
    Ejecuta SELECT ... FROM flota_asiento WHERE id IN (...) ORDER BY id
    FOR UPDATE OF flota_asiento.
    - of=('self',): bloquea solo las filas de asiento (no el servicio).
    - order_by('id'): todas las transacciones bloquean en el mismo orden,
      lo que evita deadlocks entre compras simultáneas.
    Debe llamarse dentro de transaction.atomic().
    """
    asientos = (
        Asiento.objects.select_for_update(of=('self',))
        .select_related('servicio')
        .filter(id__in=asiento_ids)
        .order_by('id')
    )
    return {asiento.id: asiento for asiento in asientos}


def _verificar_asientos(asientos):
    """
    Verificación atómica: comprueba (con las filas ya bloqueadas) que
    ningún asiento esté OCUPADO y que su servicio siga a la venta.
    Si hay problemas, lanza AsientosNoDisponibles con el detalle.
    """
    problemas = []
    for asiento in asientos:
        if asiento.estado == Asiento.Estado.OCUPADO:
            problemas.append(f'Asiento {asiento.numero} del servicio #{asiento.servicio_id} ya fue vendido.')
        elif not asiento.servicio.esta_a_la_venta:
            problemas.append(f'El servicio #{asiento.servicio_id} ya no está a la venta (salió o fue cancelado).')
    if problemas:
        raise AsientosNoDisponibles(
            detail={'detail': AsientosNoDisponibles.default_detail, 'asientos': problemas}
        )


# ---------------------------------------------------------------------
# BLOQUE: CHECKOUT (carro -> venta)
# ---------------------------------------------------------------------
@transaction.atomic
def checkout(usuario, pagar=True):
    """
    1. Bloquea el carro del usuario (evita dos checkouts simultáneos).
    2. Bloquea y verifica los asientos: ninguno puede estar OCUPADO.
    3. Crea la Venta en estado PENDIENTE y un DetalleVenta por ítem,
       CONGELANDO la tarifa vigente en ese instante.
    4. Liquida el carro (elimina sus ítems; el carro 1:1 se conserva).
    5. Si pagar=True, procesa el pago en la misma transacción: si el pago
       es rechazado se revierte TODO (el carro queda intacto).
    NOTA: hasta aquí NINGÚN asiento se ha descontado; el descuento ocurre
    solo en _pagar().
    """
    carro, _ = Carro.objects.select_for_update().get_or_create(usuario=usuario)
    items = list(carro.items.all())
    if not items:
        raise CarroVacio()

    asientos = _bloquear_asientos([item.asiento_id for item in items])
    _verificar_asientos(asientos.values())

    venta = Venta.objects.create(usuario=usuario, estado=Venta.Estado.PENDIENTE)
    detalles = []
    for item in items:
        asiento = asientos[item.asiento_id]
        detalles.append(DetalleVenta(
            venta=venta,
            asiento=asiento,
            nombre_pasajero=item.nombre_pasajero,
            tipo_documento=item.tipo_documento,
            documento_pasajero=item.documento_pasajero,
            tipo_asiento=asiento.tipo,
            precio_unitario=asiento.tarifa,  # <- precio congelado
        ))
    DetalleVenta.objects.bulk_create(detalles)

    venta.total = sum(detalle.precio_unitario for detalle in detalles)
    venta.save(update_fields=['total'])

    carro.items.all().delete()

    if pagar:
        venta = cambiar_estado(venta.id, Venta.Estado.PAGADO)
    return venta


# ---------------------------------------------------------------------
# BLOQUE: Cambio de estado (punto único de entrada)
# ---------------------------------------------------------------------
@transaction.atomic
def cambiar_estado(venta_id, nuevo_estado, observacion=''):
    """
    Bloquea la venta, valida la transición según TRANSICIONES y ejecuta
    el efecto sobre el inventario:
        -> PAGADO     : verifica y descuenta asientos, emite boletos.
        -> CANCELADO  : repone asientos (si estaba pagada) y anula boletos.
        -> COMPLETADO : marca los boletos como utilizados.
    """
    venta = Venta.objects.select_for_update().get(pk=venta_id)

    if nuevo_estado not in TRANSICIONES[venta.estado]:
        raise TransicionInvalida(
            f'No se puede pasar de {venta.estado} a {nuevo_estado}. '
            f'Permitidos: {", ".join(sorted(TRANSICIONES[venta.estado])) or "ninguno (estado final)"}.'
        )

    if nuevo_estado == Venta.Estado.PAGADO:
        _pagar(venta)
    elif nuevo_estado == Venta.Estado.CANCELADO:
        _cancelar(venta)
    elif nuevo_estado == Venta.Estado.COMPLETADO:
        _completar(venta)

    venta.estado = nuevo_estado
    if observacion:
        venta.observacion = observacion
    venta.save()
    return venta


def _pagar(venta):
    """
    -----------------------------------------------------------------
    BLOQUE: DESCUENTO ATÓMICO DE STOCK AL PASAR A PAGADO
    1. Bloquea (FOR UPDATE) los asientos de la venta.
    2. Verifica que sigan DISPONIBLES -> si no, rechaza (ROLLBACK).
    3. UPDATE masivo: los asientos pasan a OCUPADO (descuento de stock).
    4. Emite un Boleto con UUID único por cada asiento.
    -----------------------------------------------------------------
    """
    detalles = list(venta.detalles.all())
    asientos = _bloquear_asientos([detalle.asiento_id for detalle in detalles])
    _verificar_asientos(asientos.values())

    Asiento.objects.filter(id__in=asientos.keys()).update(estado=Asiento.Estado.OCUPADO)
    Boleto.objects.bulk_create([Boleto(detalle=detalle) for detalle in detalles])
    venta.pagada_en = timezone.now()


def _cancelar(venta):
    """
    -----------------------------------------------------------------
    BLOQUE: REPOSICIÓN DE STOCK AL CANCELAR
    - Si la venta estaba PENDIENTE no se había descontado nada: solo
      cambia el estado.
    - Si estaba PAGADA: solo se permite antes de la salida del bus. Los
      asientos vuelven a DISPONIBLE y los boletos quedan ANULADOS.
    -----------------------------------------------------------------
    """
    if venta.estado != Venta.Estado.PAGADO:
        return

    detalles = list(venta.detalles.all())
    asientos = _bloquear_asientos([detalle.asiento_id for detalle in detalles])
    ahora = timezone.now()
    if any(asiento.servicio.fecha_salida <= ahora for asiento in asientos.values()):
        raise TransicionInvalida('No se puede cancelar: al menos un servicio de la venta ya salió.')

    Asiento.objects.filter(id__in=asientos.keys()).update(estado=Asiento.Estado.DISPONIBLE)
    Boleto.objects.filter(detalle__venta=venta).update(estado=Boleto.Estado.ANULADO)


def _completar(venta):
    """Viaje realizado: los boletos quedan como UTILIZADOS (los asientos siguen ocupados)."""
    Boleto.objects.filter(detalle__venta=venta).update(estado=Boleto.Estado.UTILIZADO)
