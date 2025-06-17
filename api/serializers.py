from rest_framework import serializers
from main.models import (
    City, Building, HomeInformation, Home,
    ClientInformation, Client, Rasrochka,
    ExpenseType, Expense, BotUser
)
from django.conf import settings # For media URL

class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = '__all__'

class BuildingSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source='city.name', read_only=True)
    
    class Meta:
        model = Building
        fields = '__all__'

class HomeInformationSerializer(serializers.ModelSerializer):
    # Ensure URLs are absolute for external API consumption
    floor_plan_url = serializers.SerializerMethodField()
    floor_plan_drawing_url = serializers.SerializerMethodField()

    class Meta:
        model = HomeInformation
        fields = '__all__'

    def get_floor_plan_url(self, obj):
        if obj.floor_plan:
            return self.context['request'].build_absolute_uri(obj.floor_plan.url)
        return None

    def get_floor_plan_drawing_url(self, obj):
        if obj.floor_plan_drawing:
            return self.context['request'].build_absolute_uri(obj.floor_plan_drawing.url)
        return None

class HomeSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source='building.name', read_only=True)
    city_name = serializers.CharField(source='building.city.name', read_only=True)
    home_info = HomeInformationSerializer(source='home', read_only=True) # Nested serializer for HomeInformation

    class Meta:
        model = Home
        fields = '__all__'

class ClientInformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientInformation
        fields = '__all__'

class RasrochkaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rasrochka
        fields = '__all__'
        read_only_fields = ('qoldiq',) # qoldiq is calculated

class ClientSerializer(serializers.ModelSerializer):
    client_info = ClientInformationSerializer(source='client', read_only=True)
    home_info = HomeSerializer(source='home', read_only=True)
    payments = RasrochkaSerializer(many=True, read_only=True) # Nested payments

    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ('residual', 'oylik_tolov', 'count_month', 'residu', 'debt', 'created')

class ExpenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseType
        fields = '__all__'

class ExpenseSerializer(serializers.ModelSerializer):
    expense_type_name = serializers.CharField(source='expense_type.name', read_only=True)
    building_name = serializers.CharField(source='building.name', read_only=True)

    class Meta:
        model = Expense
        fields = '__all__'

class BotUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotUser
        fields = '__all__'
