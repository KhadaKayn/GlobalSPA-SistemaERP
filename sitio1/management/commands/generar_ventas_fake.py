from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from sitio1.models import Productos, Venta, DetalleVenta
import random

class Command(BaseCommand):
    help = "Genera ventas falsas para pruebas del dashboard"

    def handle(self, *args, **kwargs):

        usuario = User.objects.first()
        productos = list(Productos.objects.all())

        if not usuario:
            self.stdout.write(self.style.ERROR("❌ No existe ningún usuario en el sistema."))
            return

        if not productos:
            self.stdout.write(self.style.ERROR("❌ No hay productos en la base de datos. Inserta productos primero."))
            return

        medios_pago = ["Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Transferencia"]

        cantidad_ventas = 50

        for _ in range(cantidad_ventas):

            venta = Venta.objects.create(
                fecha=timezone.now(),
                total=0,
                usuario=usuario,
                medio_pago=random.choice(medios_pago),
                estado="completada",
            )

            total = 0
            productos_random = random.sample(productos, random.randint(1, 4))

            for producto in productos_random:
                cantidad = random.randint(1, 5)
                
                subtotal = cantidad * producto.precio_unitario

                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unidad=producto.precio_unitario,  # nombre correcto del modelo
                    costo_unitario=producto.costo_unitario if producto.costo_unitario else producto.precio_unitario * Decimal("0.7"),
                    subtotal=subtotal
                )

                total += subtotal

            venta.total = total
            venta.save()

        self.stdout.write(self.style.SUCCESS("✅ Datos de ventas generados correctamente."))
