from django import forms
from .models import  Productos, Usuario, Proveedor, Ubicacion, Categoria, Rol, Venta, DetalleVenta
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Permission
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column
from django.core.exceptions import ValidationError


# ----------------------
# FORMULARIO DE USUARIO
# ----------------------


class UsuarioForm(forms.Form):
    nombre_usuario = forms.CharField(
        label="Nombre de usuario",
        widget=forms.TextInput(attrs={'placeholder': 'Nombre de usuario', 'class': 'form-control'})
    )
    contrasena = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'placeholder': 'Contraseña', 'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('nombre_usuario', css_class='form-group col-md-6 mb-2'),
                Column('contrasena', css_class='form-group col-md-6 mb-2'),
            ),
            Submit('submit', 'Iniciar sesión', css_class='btn btn-primary mt-3')
        )


#=======================
# CREACION DE USUARIOS
#=======================
class UsuarioRegistroForm(UserCreationForm):
    nombre_completo = forms.CharField(max_length=150, required=False)
    rol = forms.ModelChoiceField(queryset=Rol.objects.all())

    class Meta:
        model = User
        fields = ['username', 'password1', 'password2', 'email']

    def __init__(self, *args, **kwargs):
        self.usuario_instance = kwargs.pop('usuario_instance', None)
        super().__init__(*args, **kwargs)
        
        # Si estamos editando, hacemos que password1 y password2 no sean requeridos
        if self.instance and self.instance.pk:
            self.fields['password1'].required = False
            self.fields['password2'].required = False

    def clean_username(self):
        username = self.cleaned_data.get('username')
        
        # Si estamos editando (hay instance.pk), excluir el usuario actual de la validación
        if self.instance and self.instance.pk:
            if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Este nombre de usuario ya está en uso.')
        else:
            # Si estamos creando, validar normalmente
            if User.objects.filter(username=username).exists():
                raise forms.ValidationError('Este nombre de usuario ya está en uso.')
        
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Si estamos editando y no hay contraseña nueva, no cambiar la contraseña
        if self.instance.pk and not self.cleaned_data.get('password1'):
            user.password = self.instance.password
        
        if commit:
            user.save()

        if self.usuario_instance:
            usuario = self.usuario_instance
        else:
            usuario = Usuario(user=user)

        usuario.nombre_completo = self.cleaned_data.get('nombre_completo')
        usuario.rol = self.cleaned_data.get('rol')
        usuario.email = user.email
        usuario.save()

        return user
# ======================
# Editar USUARIOS       
# ======================
class EditarPerfilForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ['nombre_completo', 'email', 'telefono', 'imagen']
        widgets = {
            'nombre_completo': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
        }
        
# ======================
# Creacion de roles
# ======================
class RolForm(forms.ModelForm):
    permisos = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Permisos del sistema"
    )

    class Meta:
        model = Rol
        fields = ['nombre', 'descripcion', 'permisos']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Administrador, Vendedor, etc.'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe las responsabilidades de este rol...'
            }),
        }
        
# ----------------------
# FORMULARIO DE PRODUCTOS
# ----------------------

    
class ProductosForm(forms.ModelForm):
    class Meta:
        model = Productos
        fields = [
            'sku', 'nombre', 'categoria',
            'precio_unitario', 'costo_unitario', 'stock_actual',
            'stock_minimo', 'stock_maximo', 'unidad_medida',
            'ubicacion', 'proveedor', 'activo'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Evitar negativos a nivel de widget (HTML)
        numeric_fields = [
            'precio_unitario',
            'costo_unitario',
            'stock_actual',
            'stock_minimo',
            'stock_maximo',
        ]
        for fname in numeric_fields:
            if fname in self.fields:
                self.fields[fname].widget.attrs['min'] = '0'
                self.fields[fname].widget.attrs['step'] = '0.01' if 'precio' in fname or 'costo' in fname else '1'

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('sku', css_class='form-group col-md-6 mb-2'),
            ),
            'nombre',
            'categoria',
            Row(
                Column('precio_unitario', css_class='form-group col-md-4 mb-2'),
                Column('costo_unitario', css_class='form-group col-md-4 mb-2'),
                Column('unidad_medida', css_class='form-group col-md-4 mb-2'),
            ),
            Row(
                Column('stock_actual', css_class='form-group col-md-4 mb-2'),
                Column('stock_minimo', css_class='form-group col-md-4 mb-2'),
                Column('stock_maximo', css_class='form-group col-md-4 mb-2'),
            ),
            'ubicacion',
            'proveedor',
            'activo',
            Submit('submit', 'Guardar', css_class='btn btn-primary mt-3')
        )

    # --------- Validaciones de negocio ---------

    def clean_precio_unitario(self):
        precio = self.cleaned_data.get('precio_unitario')
        if precio is not None and precio < 0:
            raise ValidationError("El precio unitario no puede ser negativo.")
        return precio

    def clean_costo_unitario(self):
        costo = self.cleaned_data.get('costo_unitario')
        if costo is not None and costo < 0:
            raise ValidationError("El costo unitario no puede ser negativo.")
        return costo

    def clean_stock_actual(self):
        stock = self.cleaned_data.get('stock_actual')
        if stock is not None and stock < 0:
            raise ValidationError("El stock actual no puede ser negativo.")
        return stock

    def clean_stock_minimo(self):
        minimo = self.cleaned_data.get('stock_minimo')
        if minimo is not None and minimo < 0:
            raise ValidationError("El stock mínimo no puede ser negativo.")
        return minimo

    def clean_stock_maximo(self):
        maximo = self.cleaned_data.get('stock_maximo')
        if maximo is not None and maximo < 0:
            raise ValidationError("El stock máximo no puede ser negativo.")
        return maximo

    def clean_sku(self):
        sku = self.cleaned_data.get('sku')
        if not sku:
            return sku  # permites SKU vacío, si eso está OK en tu lógica

        qs = Productos.objects.filter(sku__iexact=sku)
        # Si estás editando, excluye el propio producto
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("Ya existe un producto con este SKU.")

        return sku
    
    def clean(self):
        cleaned = super().clean()
        minimo = cleaned.get('stock_minimo')
        maximo = cleaned.get('stock_maximo')

        if minimo is not None and maximo is not None and maximo < minimo:
            raise ValidationError("El stock máximo no puede ser menor que el stock mínimo.")

        return cleaned


# formulacios para los demas modelos

# ======================
# FORMULARIO CATEGORIA
# ======================
class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nombre', 'descripcion']

# ======================
# FORMULARIO UBICACION
# ======================
class UbicacionForm(forms.ModelForm):
    class Meta:
        model = Ubicacion
        fields = ['direccion', 'comuna', 'region', 'descripcion']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('direccion', css_class='form-group col-md-12 mb-2'),
            ),
            Row(
                Column('comuna', css_class='form-group col-md-6 mb-2'),
                Column('region', css_class='form-group col-md-6 mb-2'),
            ),
            'descripcion',
            Submit('submit', 'Guardar', css_class='btn btn-primary mt-3')
        )

# ======================
# FORMULARIO PROVEEDOR
# ======================
class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ['nombre', 'telefono', 'correo', 'direccion', 'observaciones']

# ======================
# FORMULARIO PARA VENTAS
# ======================

class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ['medio_pago']
        widgets = {
            'medio_pago': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Efectivo, Tarjeta, Transferencia'
            }),
        }

class DetalleVentaForm(forms.ModelForm):
    class Meta:
        model = DetalleVenta
        fields = ['producto', 'cantidad', 'precio_unidad']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].widget.attrs.update({'class': 'form-select'})
        self.fields['cantidad'].widget.attrs.update({'class': 'form-control', 'min': 1})
        self.fields['precio_unidad'].widget.attrs.update({
            'class': 'form-control',
            'readonly': True
        })



DetalleVentaFormSet = inlineformset_factory(
    Venta, DetalleVenta,
    form=DetalleVentaForm,
    extra=1,
    can_delete=True
)
