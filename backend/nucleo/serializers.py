# backend/nucleo/serializers.py
# Converte os modelos do app 'nucleo' para o formato JSON.
from rest_framework import serializers
from .models import Usuario, Perfil, Permissao, LogAtividadeUsuario

class UsuarioSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo customizado de Usuário.
    Importante: O campo 'password' é write-only para segurança.
    """
    class Meta:
        model = Usuario
        # Lista explícita de campos para não expor dados sensíveis como o hash da senha.
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 
            'cpf', 'telefone', 'is_staff', 'is_active', 'is_data_admin', 
            'perfil', 'date_joined', 'password'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        # Sobrescreve o método create para hashear a senha corretamente.
        user = Usuario.objects.create_user(**validated_data)
        return user

class PerfilSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Perfil.
    """
    class Meta:
        model = Perfil
        fields = '__all__'

class PermissaoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Permissao.
    """
    class Meta:
        model = Permissao
        fields = '__all__'

class LogAtividadeUsuarioSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo LogAtividadeUsuario.
    """
    class Meta:
        model = LogAtividadeUsuario
        fields = '__all__'
