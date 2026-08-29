from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)

    def validate(self, attributes):
        user = authenticate(
            request=self.context["request"],
            username=attributes["username"],
            password=attributes["password"],
        )
        if user is None or not user.is_active:
            raise AuthenticationFailed("Invalid credentials.")
        attributes["user"] = user
        return attributes


def serialize_session_user(user) -> dict[str, str]:
    return {
        "id": str(user.id),
        "username": user.get_username(),
        "role": user.role,
        "organization_id": str(user.organization_id),
    }
