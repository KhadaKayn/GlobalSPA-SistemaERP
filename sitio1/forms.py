from django import forms
from .models import  Productos, Usuario, Proveedor, Ubicacion, Categoria, Rol, Venta, DetalleVenta
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Permission
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column


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
