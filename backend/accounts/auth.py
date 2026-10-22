from django.contrib.auth import get_user_model
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from audit.services import log as audit_log

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['login'] = serializers.CharField()
        del self.fields[self.username_field]

    def validate(self, attrs):
        login = attrs.pop('login')
        request = self.context.get('request')
        user = User.objects.filter(username=login).first() or User.objects.filter(email=login).first()
        attrs[self.username_field] = user.username if user else login
        try:
            data = super().validate(attrs)
        except exceptions.AuthenticationFailed:
            audit_log(
                request, 'login_echec', cible=user, details={'login': login},
                etablissement=getattr(user, 'etablissement', None),
            )
            raise
        user = self.user
        if user.role == 'admin' and user.validation_status == 'pending':
            raise serializers.ValidationError("Votre compte est en attente de validation par le superadministrateur.")
        if user.role == 'admin' and user.validation_status == 'rejected':
            raise serializers.ValidationError("Votre compte a été rejeté. Contactez le support.")
        audit_log(request, 'login_succes', cible=user, acteur=user)
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
