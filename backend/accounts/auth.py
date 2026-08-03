from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['login'] = serializers.CharField()
        del self.fields[self.username_field]

    def validate(self, attrs):
        login = attrs.pop('login')
        user = User.objects.filter(username=login).first()
        if not user:
            user = User.objects.filter(email=login).first()
        if user:
            attrs[self.username_field] = user.username
        data = super().validate(attrs)
        user = self.user
        if user.role == 'admin' and user.validation_status == 'pending':
            raise serializers.ValidationError("Votre compte est en attente de validation par le superadministrateur.")
        if user.role == 'admin' and user.validation_status == 'rejected':
            raise serializers.ValidationError("Votre compte a été rejeté. Contactez le support.")
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
