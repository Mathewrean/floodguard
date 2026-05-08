"""
User Profile Serializers for API
"""

from rest_framework import serializers
from .models import UserProfile
from django.contrib.auth.models import User


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile updates (phone, preferences)"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'username', 'email', 'role', 'phone_number',
            'phone_verified', 'sms_enabled'
        ]
        read_only_fields = ['username', 'email', 'role', 'phone_verified']
    
    def validate_phone_number(self, value):
        """Validate phone number format (E.164 international format)"""
        if not value:
            return value
        
        # E.164 format: +[country code][number] (max 15 digits after +)
        cleaned = value.strip().replace(' ', '').replace('-', '')
        
        if not cleaned.startswith('+'):
            raise serializers.ValidationError(
                "Phone number must be in international format (e.g., +254712345678)"
            )
        
        # Check length (E.164 max is 15 digits after +)
        digits = cleaned[1:]
        if not digits.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits after +")
        if len(digits) < 10 or len(digits) > 15:
            raise serializers.ValidationError(
                "Phone number must be between 10 and 15 digits after country code"
            )
        
        return cleaned
