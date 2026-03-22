from rest_framework import serializers
from ..models import EmailTemplate


class EmailTemplateMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = ['id', 'name', 'subject']


class EmailTemplateDisplaySerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = '__all__'
        read_only_fields = ['created_at', 'modified_at']


class EmailTemplateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = '__all__'

    def validate_name(self, value):
        instance = getattr(self, 'instance', None)
        qs = EmailTemplate.objects.all()
        if instance:
            qs = qs.exclude(id=instance.id)
        if qs.filter(name=value).exists():
            raise serializers.ValidationError('An email template with this name already exists.')
        return value

    def create(self, validated_data):
        return EmailTemplate.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def to_representation(self, instance):
        return EmailTemplateDisplaySerializer(instance, context=self.context).data