import json
import re
import math
import asyncio
import aiohttp
import openpyxl
import os
import shutil
import requests
import tempfile
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal

from django.db.models import Sum, Q, Max
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.template.loader import render_to_string
from django.db import transaction
from django.http import FileResponse, Http404

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth

from main.models import (
    City, Building, HomeInformation, Home,
    ClientInformation, Client, Rasrochka,
    ExpenseType, Expense, BotUser, ClientTrash
)
from .serializers import (
    CitySerializer, BuildingSerializer, HomeInformationSerializer, HomeSerializer,
    ClientInformationSerializer, ClientSerializer, RasrochkaSerializer,
    ExpenseTypeSerializer, ExpenseSerializer, BotUserSerializer
)
from django.core.files.base import ContentFile
import logging
logger = logging.getLogger(__name__)

# --- Helper Functions (Moved from main/views.py or adapted) ---

def normalize_phone(phon):
    if not phon:
        return None
    if isinstance(phon, float):
        phon = str(int(phon))
    phone = str(phon)
    digits = re.sub(r'\D', '', phone)
    if len(digits) > 9:
        digits = digits[-9:]
    if len(digits) == 9:
        return '+998' + digits
    elif len(digits) == 12 and digits.startswith('998'):
        return '+' + digits
    else:
        return None

async def send_sms(phone, sms: str):
    if not phone:
        return False
    try:
        url = "https://notify.eskiz.uz/api/message/sms/send"
        params = {
            "mobile_phone": f"{phone}",
            "message": f"{sms}",
            "from": "4546",
        }
        headers = {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDk5NjUyOTAsImlhdCI6MTc0NzM3MzI5MCwicm9sZSI6InVzZXIiLCJzaWduIjoiZmY4Mzk1ZDBjOWE2NmIzYjEzYjkzODUxNzU1Njc2NDZhMzc0NGVlMThiMDM0MjNlYmJlYTZlOTc5NjNjNGM1OSIsInN1YiI6Ijc3NTkifQ.WmTxpM_j2Yzyl0kaonaTBMoUCjhTp5OBHatR9KCZXx0",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, data=params, headers=headers, ssl=False
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"SMS sent, response: {data}")
                    return True
                else:
                    logger.info(
                        f"SMS send error:\nstatus: {response.status}\nresponse: {await response.text()}"
                    )
                    return False
    except Exception as e:
        logger.error(f"SMS send exception: {e}")
        return False

def number_to_words_uz(number):
    units = [
        "", "бир", "икки", "уч", "тўрт", "беш", "олти", "етти", "саккиз", "тўққиз",
    ]
    tens = [
        "", "ўн", "йигирма", "ўттиз", "қирқ", "эллик", "олтимиш", "етмиш", "саксон", "тўқсон",
    ]
    scales = ["", "минг", "миллион", "миллиард", "триллион", "квадриллион"]

    def integer_to_words(num):
        if num == 0:
            return "нол"
        words = []
        num_str = str(num)[::-1]
        groups = [num_str[i : i + 3] for i in range(0, len(num_str), 3)]

        for idx, group in enumerate(groups):
            group_word = []
            hundreds, remainder = divmod(int(group[::-1]), 100)
            tens_unit = remainder % 10
            tens_place = remainder // 10

            if hundreds > 0:
                group_word.append(units[hundreds] + " юз")

            if tens_place > 0:
                group_word.append(tens[tens_place])

            if tens_unit > 0:
                group_word.append(units[tens_unit])

            if group_word and scales[idx]:
                group_word.append(scales[idx])

            words = group_word + words

        return " ".join(words)

    integer_part = int(number)
    fractional_part = round(number % 1, 2)
    fractional_str = str(fractional_part)[2:] if fractional_part > 0 else None

    result = integer_to_words(integer_part)
    if fractional_str:
        result += f" бутун {integer_to_words(int(fractional_str))}"

    return result

def qisqartirish(full_name):
    parts = full_name.split()
    if len(parts) == 3 or len(parts) == 4:
        return f"{parts[0]} {parts[1][0].upper()}. {parts[2][0].upper()}."
    elif len(parts) == 2:
        return f"{parts[0]} {parts[1][0].upper()}."
    elif len(parts) == 1:
        return parts[0]
    return full_name

def save_image_from_cell(cell, home_info, field_name, filename, row_idx):
    """
    Helper function to save image from Excel cell (URL or local path)
    """
    try:
        val = cell.value
        image_data = None
        
        if isinstance(val, str):
            if val.startswith('http'):
                response = requests.get(val, timeout=30)
                if response.status_code == 200:
                    image_data = response.content
                else:
                    logger.warning(f"Row {row_idx}: Failed to download image from URL: {val}")
                    return False
            elif os.path.exists(val):
                with open(val, 'rb') as f:
                    image_data = f.read()
            else:
                logger.warning(f"Row {row_idx}: File not found at path: {val}")
                return False
        elif hasattr(cell, 'hyperlink') and cell.hyperlink:
            url = cell.hyperlink.target
            if url.startswith('http'):
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    image_data = response.content
                else:
                    logger.warning(f"Row {row_idx}: Failed to download image from hyperlink: {url}")
                    return False
        
        if image_data:
            field = getattr(home_info, field_name)
            field.save(filename, ContentFile(image_data), save=True)
            return True
            
    except Exception as e:
        logger.error(f"Row {row_idx}: Error saving image from cell: {e}")
        return False
    
    return False

# --- ViewSets for standard CRUD operations ---

class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer
    permission_classes = [IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if Building.objects.filter(city=instance).exists():
            return Response(
                {"detail": "Bu shaharga bog'langan binolar mavjud. Avval ularni o'chiring."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    permission_classes = [IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if Home.objects.filter(building=instance).exists():
            return Response(
                {"detail": "Bu binoga bog'langan uylar mavjud. Avval ularni o'chiring."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

class HomeInformationViewSet(viewsets.ModelViewSet):
    queryset = HomeInformation.objects.all()
    serializer_class = HomeInformationSerializer
    permission_classes = [IsAuthenticated]

class HomeViewSet(viewsets.ModelViewSet):
    queryset = Home.objects.all()
    serializer_class = HomeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        building_id = self.request.query_params.get("building")
        city_id = self.request.query_params.get("city")
        status_param = self.request.query_params.get("status")
        filters = {}
        if city_id and city_id.isdigit():
            filters["building__city__id"] = city_id
        if building_id and building_id.isdigit():
            filters["building__id"] = building_id
        if status_param:
            filters['home__busy'] = True if status_param == 'occupied' else False
        
        if filters:
            queryset = queryset.filter(**filters)
        return queryset.order_by("-created")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if Client.objects.filter(home=instance).exists():
            return Response(
                {"detail": "Bu uyga bog'langan shartnomalar mavjud. Avval ularni o'chiring."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Also delete the associated HomeInformation
        home_info = instance.home
        response = super().destroy(request, *args, **kwargs)
        home_info.delete()
        return response

    @action(detail=False, methods=['get'], url_path='by-building-padez')
    def by_building_padez(self, request):
        building_id = request.query_params.get('building')
        padez_number = request.query_params.get('padez')

        if not building_id or not padez_number:
            return Response(
                {"detail": "Building ID and Padez number are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        homes = HomeInformation.objects.filter(
            home_instances__building_id=building_id,
            padez_number=padez_number
        )
        serializer = HomeInformationSerializer(homes, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        building_pk = request.data.get("building_sel")
        
        if not building_pk:
            return Response({"detail": "Bino tanlanmadi."}, status=status.HTTP_400_BAD_REQUEST)

        building = get_object_or_404(Building, pk=building_pk)
        padez_counts = building.padez_home
        
        created_homes = []
        errors = []

        with transaction.atomic():
            for padez_number, apartment_count in enumerate(padez_counts, start=1):
                for home_number_in_padez in range(1, int(apartment_count) + 1):
                    try:
                        # Form ma'lumotlarini olish
                        home_mkv = request.data.get(f"home_maydon_{padez_number}_{home_number_in_padez}")
                        home_mkvp = request.data.get(f"home_mkv_{padez_number}_{home_number_in_padez}")
                        home_floor = request.data.get(f"home_floor_{padez_number}_{home_number_in_padez}")
                        home_num = request.data.get(f"home_num_{padez_number}_{home_number_in_padez}")
                        home_xona = request.data.get(f"home_xona_{padez_number}_{home_number_in_padez}")
                        floor_plan = request.FILES.get(f"floor_plan_{padez_number}_{home_number_in_padez}")
                        home_cadastral = request.FILES.get(f"home_cadastral_{padez_number}_{home_number_in_padez}")
                        
                        if not all([home_mkv, home_floor, home_num, home_xona]):
                            errors.append(f"Padez {padez_number}, xonadon {home_number_in_padez} uchun ma'lumotlar to'liq emas.")
                            continue
                        
                        home_mkv_float = float(str(home_mkv).replace(',', '.'))
                        home_mkvp_int = int(str(home_mkvp).replace(' ', '') or 0)
                        home_floor_int = int(home_floor)
                        home_xona_int = int(home_xona)
                        
                        hinfo = HomeInformation.objects.create(
                            padez_number=padez_number,
                            home_number=home_num,
                            field=home_mkv_float,
                            price=home_mkvp_int,
                            busy=False,
                            home_floor=home_floor_int,
                            xona=home_xona_int,
                            floor_plan=floor_plan,
                            floor_plan_drawing=home_cadastral
                        )
                        
                        home = Home.objects.create(building=building, home=hinfo)
                        hinfo.home_model_id = home.pk
                        hinfo.save()
                        created_homes.append(home)
                    except (ValueError, TypeError) as e:
                        errors.append(f"Padez {padez_number}, xonadon {home_number_in_padez} uchun ma'lumot formatida xatolik: {e}")
                        continue
                    except Exception as e:
                        errors.append(f"Padez {padez_number}, xonadon {home_number_in_padez} uchun xatolik yuz berdi: {e}")
                        continue
            
            if created_homes:
                building.status = True
                building.save()
                serializer = self.get_serializer(created_homes, many=True)
                return Response({"detail": "Xonadonlar muvaffaqiyatli yaratildi.", "homes": serializer.data, "errors": errors}, status=status.HTTP_201_CREATED)
            else:
                transaction.set_rollback(True)
                return Response({"detail": "Xonadonlar yaratilmadi. Xatoliklar mavjud.", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        home_instance = self.get_object()
        data = request.data
        
        try:
            name = data.get("home_number") # Changed from "home"
            maydon = data.get("field") # Changed from "maydon"
            price = data.get("price")
            check = data.get("busy") # Changed from "check"
            floor = data.get("home_floor") # Changed from "floor"
            honalar = data.get("xona") # Changed from "honalar"
            floor_plan = request.FILES.get("floor_plan") # Changed from "home_plan"
            floor_plan_drawing = request.FILES.get("floor_plan_drawing")
            
            if not all([name, maydon, price, floor, honalar]):
                return Response({"detail": "Barcha ma'lumotlarni to'ldiring."}, status=status.HTTP_400_BAD_REQUEST)
            
            number_str = str(maydon).replace(",", ".")
            
            home_instance.home.home_number = name
            home_instance.home.field = float(number_str)
            home_instance.home.price = int(price)
            home_instance.home.home_floor = int(floor)
            home_instance.home.xona = int(honalar)
            home_instance.home.busy = check
            
            if floor_plan_drawing:
                if home_instance.home.floor_plan_drawing:
                    home_instance.home.floor_plan_drawing.delete(save=False)
                home_instance.home.floor_plan_drawing = floor_plan_drawing
            if floor_plan:
                if home_instance.home.floor_plan:
                    home_instance.home.floor_plan.delete(save=False)
                home_instance.home.floor_plan = floor_plan
            
            home_instance.home.save()
            home_instance.save()
            
            serializer = self.get_serializer(home_instance)
            return Response({"detail": "Xonadon muvaffaqiyatli tahrirlandi.", "home": serializer.data}, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": f"Noto'g'ri ma'lumotlar kiritildi: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Xatolik yuz berdi: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClientInformationViewSet(viewsets.ModelViewSet):
    queryset = ClientInformation.objects.all()
    serializer_class = ClientInformationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        filter_val = self.request.query_params.get("filter")

        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) | Q(phone__icontains=search)
            )
        elif filter_val and filter_val.isdigit() and filter_val in ["0", "1", "2", "3", "4"]:
            status_map = {
                "0": "Telegramda",
                "1": "Instagramda",
                "2": "YouTubeda",
                "3": "Odamlar orasida",
                "4": "Xech qayerda",
            }
            queryset = queryset.filter(heard=status_map[filter_val])
        
        return queryset.order_by("-created")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if Client.objects.filter(client=instance).exists():
            return Response(
                {"detail": "Mijozni olib tashlash mumkin emas. Sababi bu mijoz nomiga xonadan rasmiylashtirilgan."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'], url_path='send-sms')
    def send_sms_to_clients(self, request):
        sms_text = request.data.get("sms_text")
        recipient_type = request.data.get("recipient_type")
        custom_phone = request.data.get("custom_phone")

        if not sms_text:
            return Response({"detail": "SMS matni kiritilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        clients_to_send = ClientInformation.objects.filter(phone__isnull=False)
        if recipient_type == "all":
            pass # All clients
        elif recipient_type == "telegram":
            clients_to_send = clients_to_send.filter(heard="Telegramda")
        elif recipient_type == "instagram":
            clients_to_send = clients_to_send.filter(heard="Instagramda")
        elif recipient_type == "youtube":
            clients_to_send = clients_to_send.filter(heard="YouTubeda")
        elif recipient_type == "people":
            clients_to_send = clients_to_send.filter(heard="Odamlar orasida")
        elif recipient_type == "custom" and custom_phone:
            phone_clean = normalize_phone(custom_phone)
            if not phone_clean:
                return Response({"detail": "Noto'g'ri telefon raqami formati."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                asyncio.run(send_sms(phone_clean, sms_text))
                return Response({"detail": "SMS muvaffaqiyatli yuborildi."}, status=status.HTTP_200_OK)
            except Exception as e:
                logger.error(f"Error sending custom SMS: {e}")
                return Response({"detail": f"SMS yuborishda xatolik: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({"detail": "Noto'g'ri qabul qiluvchi turi yoki telefon raqami."}, status=status.HTTP_400_BAD_REQUEST)

        sent_count = 0
        for client in clients_to_send:
            try:
                if asyncio.run(send_sms(client.phone, sms_text)):
                    sent_count += 1
            except Exception as e:
                logger.error(f"Error sending SMS to client {client.id}: {e}")
                continue
        return Response({"detail": f"{sent_count} ta mijozga SMS yuborildi."}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        full_name = request.data.get("full_name")
        phone = request.data.get("phone")
        phone2 = request.data.get("phone2", "")
        heard = request.data.get("heard")

        if not full_name:
            return Response({"detail": "Mijoz ismi kiritilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        if not phone:
            return Response({"detail": "Telefon raqami kiritilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        if not heard:
            return Response({"detail": "Qayerda eshitgani kiritilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        phone_clean = normalize_phone(phone)
        phone2_clean = normalize_phone(phone2) if phone2 else None
        
        if not phone_clean:
            return Response({"detail": "Telefon raqami noto'g'ri formatda."}, status=status.HTTP_400_BAD_REQUEST)

        existing_client = ClientInformation.objects.filter(
            Q(phone=phone_clean) | Q(full_name=full_name)
        ).first()
        
        if existing_client:
            return Response({"detail": "Bu mijoz allaqachon mavjud."}, status=status.HTTP_409_CONFLICT)

        client_info = ClientInformation.objects.create(
            full_name=full_name, 
            phone=phone_clean, 
            phone2=phone2_clean,
            heard=heard
        )
        serializer = self.get_serializer(client_info)
        return Response({"detail": "Mijoz muvaffaqiyatli yaratildi.", "client": serializer.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        client_instance = self.get_object()
        data = request.data

        name = data.get("full_name")
        phone = data.get("phone")
        phone2 = data.get("phone2", "")
        heard = data.get("heard")

        if not name:
            return Response({"detail": "Mijoz ismi kiritilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        if not phone:
            return Response({"detail": "Telefon raqami kiritilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        phone_clean = normalize_phone(phone)
        phone2_clean = normalize_phone(phone2) if phone2 else None
        
        if not phone_clean:
            return Response({"detail": "Telefon raqami noto'g'ri formatda."}, status=status.HTTP_400_BAD_REQUEST)

        client_instance.full_name = name
        client_instance.phone = phone_clean
        client_instance.phone2 = phone2_clean
        client_instance.heard = heard
        client_instance.save()
        
        serializer = self.get_serializer(client_instance)
        return Response({"detail": "Mijoz ma'lumotlari muvaffaqiyatli yangilandi.", "client": serializer.data}, status=status.HTTP_200_OK)


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.query_params.get("q")
        city_id = self.request.query_params.get("city")
        building_id = self.request.query_params.get("building")
        debt_status = self.request.query_params.get("debt")
        status_param = self.request.query_params.get("status")

        filters = {}
        if city_id:
            filters["home__building__city__id"] = city_id
        if building_id:
            filters["home__building__id"] = building_id
        if debt_status:
            filters["debt"] = debt_status.lower() == "true"
        if status_param and status_param in ["0", "1", "2", "3"]:
            status_map = {
                "0": "Bekor qilingan",
                "1": "Rasmiylashtirilmoqda",
                "2": "Rasmiylashtirilgan",
                "3": "Tugallangan",
            }
            filters["status"] = status_map[status_param]
        
        if filters:
            queryset = queryset.filter(**filters)

        if q:
            queryset = queryset.filter(
                Q(passport__icontains=q) | 
                Q(client__full_name__icontains=q) |
                Q(client__phone__icontains=q) |
                Q(client__phone2__icontains=q) |
                Q(contract__icontains=q),
            )
        return queryset.order_by("-created")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        rasrochka_entries = Rasrochka.objects.filter(client=instance).order_by("date")
        total_amount = sum(float(p.amount) for p in rasrochka_entries)
        total_paid = sum(float(p.amount_paid) for p in rasrochka_entries)
        total_remaining = sum(float(p.qoldiq) for p in rasrochka_entries)
        
        initial_payment = rasrochka_entries.filter(month=0).first()
        initial_payment_amount = float(initial_payment.amount) if initial_payment else 0
        
        monthly_payment = rasrochka_entries.filter(month__gt=0).first()
        monthly_payment_amount = float(monthly_payment.amount) if monthly_payment else 0
        
        next_unpaid = rasrochka_entries.filter(qoldiq__gt=0).order_by('month').first()
        next_unpaid_month = next_unpaid.month if next_unpaid else None
        next_unpaid_amount = float(next_unpaid.qoldiq) if next_unpaid else 0
        
        remaining_months = rasrochka_entries.filter(qoldiq__gt=0).count()
        is_in_debt = total_remaining > 0

        data['payment_info'] = {
            'initial_payment': initial_payment_amount,
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_remaining': total_remaining,
            'monthly_payment': monthly_payment_amount,
            'next_unpaid_month': next_unpaid_month,
            'next_unpaid_amount': next_unpaid_amount,
            'remaining_months': remaining_months,
            'is_in_debt': is_in_debt,
            'active_contracts': Client.objects.filter(debt=True).count(),
            'total_debt': float(Client.objects.filter(debt=True).aggregate(total=Sum('residual'))['total'] or 0),
            'debtors_count': Client.objects.filter(debt=True).count()
        }
        return Response(data)

    def create(self, request, *args, **kwargs):
        data = request.data
        
        building_sel = data.get("building")
        padez_sel = data.get("padez_number")
        selected_home_number = data.get("home_number")
        client_name = data.get("full_name")
        client_phone = data.get("phone")
        client_phone2 = data.get("phone2", "")
        client_passport = data.get("passport")
        passport_muddat = data.get("passport_muddat")
        given = data.get("given")
        location = data.get("location")
        location2 = data.get("location2")
        client_payment_term = data.get("term")
        client_advance_payment = data.get("payment")
        status_contract = data.get("status")
        pay_date_day = data.get("pay_date")
        home_price_per_sqm = data.get("price")
        heard = data.get("heard")
        contract_date_str = data.get("created")

        if not all([building_sel, padez_sel, selected_home_number, client_name, client_phone, client_passport, client_payment_term, client_advance_payment, status_contract, pay_date_day, home_price_per_sqm]):
            return Response({"detail": "Barcha majburiy maydonlar to'ldirilishi shart."}, status=status.HTTP_400_BAD_REQUEST)

        contract_datetime = timezone.now()
        if contract_date_str:
            try:
                contract_date_obj = datetime.strptime(contract_date_str, '%Y-%m-%d').date()
                contract_datetime = timezone.make_aware(datetime.combine(contract_date_obj, datetime.min.time()))
            except ValueError:
                return Response({"detail": "Shartnoma sanasi noto'g'ri formatda."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client_phone = normalize_phone(client_phone)
            client_phone2 = normalize_phone(client_phone2) if client_phone2 else None
            client_advance_payment = Decimal(str(client_advance_payment).replace(" ", "") or 0)
            client_payment_term = int(client_payment_term or 0)
            home_price_per_sqm = Decimal(str(home_price_per_sqm).replace(" ", "") or 0)
            pay_date_day = int(pay_date_day or 15)
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return Response({"detail": "Raqamli maydonlar noto'g'ri formatda."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not client_phone:
            return Response({"detail": "Telefon raqami noto'g'ri formatda."}, status=status.HTTP_400_BAD_REQUEST)

        home_instance_query = Home.objects.filter(
            building_id=building_sel,
            home__padez_number=padez_sel,
            home__home_number=selected_home_number,
        )
        
        if not home_instance_query.exists():
            return Response({"detail": "Tanlangan uy topilmadi."}, status=status.HTTP_404_NOT_FOUND)
                
        home = home_instance_query.first()
        
        if home.home.busy:
            return Response({"detail": "Bu uy allaqachon band."}, status=status.HTTP_400_BAD_REQUEST)
            
        if home_price_per_sqm and home.home.price != home_price_per_sqm:
            home.home.price = home_price_per_sqm
            home.home.save()
                
        mijoz = ClientInformation.objects.filter(
            Q(full_name=client_name) & Q(phone=client_phone)
        ).first()
        
        if mijoz:
            mijoz.full_name = client_name
            mijoz.phone = client_phone
            mijoz.phone2 = client_phone2
            if heard:
                mijoz.heard = heard
            mijoz.save()
        else:
            mijoz = ClientInformation.objects.create(
                full_name=client_name, 
                phone=client_phone,
                phone2=client_phone2,
                heard=heard or "Xech qayerda"
            )

        total_price = Decimal(str(home.home.field)) * Decimal(str(home.home.price))
        
        with transaction.atomic():
            max_contract = Client.objects.aggregate(Max('contract'))['contract__max'] or 0
            contract_number = max_contract + 1

            contract_obj = None
            if client_payment_term != 0:
                if client_advance_payment != 0:
                    if client_advance_payment == total_price:
                        contract_obj = Client.objects.create(
                            client=mijoz,
                            contract=contract_number,
                            home=home,
                            passport=client_passport,
                            passport_muddat=passport_muddat,
                            given=given,
                            location=location,
                            location2=location2,
                            term=0,
                            payment=client_advance_payment,
                            residual=0,
                            oylik_tolov=0,
                            count_month=0,
                            residu=0,
                            status="Tugallangan",
                            debt=False,
                            pay_date=pay_date_day,
                            home_price=total_price,
                            created=contract_datetime,
                        )
                        Rasrochka.objects.create(
                            client=contract_obj, 
                            amount=client_advance_payment, 
                            month=0, 
                            amount_paid=client_advance_payment, 
                            qoldiq=0, 
                            date=contract_datetime
                        )
                    else:
                        res = total_price - client_advance_payment
                        cp = client_payment_term
                        exact_result = res / Decimal(cp)
                        rounded_result = Decimal(math.floor(float(exact_result) / 100000) * 100000)

                        contract_obj = Client.objects.create(
                            client=mijoz,
                            contract=contract_number,
                            home=home,
                            passport=client_passport,
                            passport_muddat=passport_muddat,
                            given=given,
                            location=location,
                            location2=location2,
                            term=client_payment_term,
                            payment=client_advance_payment,
                            residual=res,
                            oylik_tolov=rounded_result,
                            count_month=client_payment_term,
                            residu=0,
                            status=status_contract,
                            debt=True,
                            pay_date=pay_date_day,
                            home_price=total_price,
                            created=contract_datetime,
                        )
                        
                        Rasrochka.objects.create(
                            client=contract_obj,
                            amount=client_advance_payment,
                            month=0, 
                            amount_paid=client_advance_payment,
                            qoldiq=0,
                            date=contract_datetime
                        )
                        
                        start_date = contract_datetime.replace(day=pay_date_day)
                        if start_date.day < contract_datetime.day:
                            start_date = start_date + relativedelta(months=1)

                        remaining = res
                        for month_num in range(1, client_payment_term + 1):
                            if month_num == client_payment_term:
                                amount = remaining
                            else:
                                amount = min(rounded_result, remaining)
                            
                            payment_date = start_date + relativedelta(months=month_num)
                            try:
                                payment_date = payment_date.replace(day=pay_date_day)
                            except ValueError:
                                last_day = (payment_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                                payment_date = payment_date.replace(day=last_day.day)
                            
                            Rasrochka.objects.create(
                                client=contract_obj,
                                amount=amount,
                                month=month_num, 
                                amount_paid=0,
                                qoldiq=amount,
                                date=payment_date
                            )
                            remaining -= amount

                        contract_obj.oylik_tolov = rounded_result
                        contract_obj.save()
                else:
                    res = total_price
                    cp = client_payment_term
                    exact_result = res / Decimal(cp)
                    rounded_result = Decimal(math.floor(float(exact_result) / 100000) * 100000)
                    
                    contract_obj = Client.objects.create(
                        client=mijoz,
                        contract=contract_number,
                        home=home,
                        passport=client_passport,
                        passport_muddat=passport_muddat,
                        given=given,
                        location=location,
                        location2=location2,
                        term=client_payment_term,
                        payment=0,
                        residual=res,
                        oylik_tolov=rounded_result,
                        count_month=client_payment_term,
                        residu=0,
                        status=status_contract,
                        debt=True,
                        pay_date=pay_date_day,
                        home_price=total_price,
                        created=contract_datetime,
                    )
                    
                    start_date = contract_datetime.replace(day=pay_date_day)
                    if start_date.day < contract_datetime.day:
                        start_date = start_date + relativedelta(months=1)

                    remaining = res
                    for month_num in range(1, client_payment_term + 1):
                        if month_num == client_payment_term:
                            amount = remaining
                        else:
                            amount = min(rounded_result, remaining)
                        
                        payment_date = start_date + relativedelta(months=month_num)
                        try:
                            payment_date = payment_date.replace(day=pay_date_day)
                        except ValueError:
                            last_day = (payment_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                            payment_date = payment_date.replace(day=last_day.day)
                        
                        Rasrochka.objects.create(
                            client=contract_obj,
                            amount=amount,
                            month=month_num, 
                            amount_paid=0,
                            qoldiq=amount,
                            date=payment_date
                        )
                        remaining -= amount

                    contract_obj.oylik_tolov = rounded_result
                    contract_obj.save()
                
                home.home.busy = True
                home.home.save()
            else:
                if client_advance_payment == total_price:
                    contract_obj = Client.objects.create(
                        client=mijoz,
                        contract=contract_number,
                        home=home,
                        passport=client_passport,
                        passport_muddat=passport_muddat,
                        given=given,
                        location=location,
                        location2=location2,
                        term=0,
                        payment=client_advance_payment,
                        residual=0,
                        oylik_tolov=0,
                        count_month=0,
                        residu=0,
                        status="Tugallangan",
                        debt=False,
                        pay_date=pay_date_day,
                        home_price=total_price,
                        created=contract_datetime,
                    )
                    Rasrochka.objects.create(
                        client=contract_obj,
                        amount=client_advance_payment,
                        month=0, 
                        amount_paid=client_advance_payment,
                        qoldiq=0,
                        date=contract_datetime
                    )
                    home.home.busy = True
                    home.home.save()
                else:
                    return Response({"detail": "To'lov muddati 0 bo'lsa, to'liq to'lov qilinishi kerak."}, status=status.HTTP_400_BAD_REQUEST)
            
            if contract_obj.residual <= 0:
                contract_obj.debt = False
                contract_obj.status = "Tugallangan"
                contract_obj.residual = 0
                contract_obj.residu = 0
                contract_obj.save()
            
            serializer = self.get_serializer(contract_obj)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        contract = self.get_object()
        data = request.data

        old_status = contract.status
        new_status = data.get('status', old_status)

        with transaction.atomic():
            client_info = contract.client
            client_info.full_name = data.get('full_name', client_info.full_name)
            client_info.phone = normalize_phone(data.get('phone', client_info.phone))
            client_info.phone2 = normalize_phone(data.get('phone2', client_info.phone2))
            client_info.save()

            contract.passport = data.get('passport', contract.passport)
            contract.passport_muddat = data.get('passport_muddat', contract.passport_muddat)
            contract.given = data.get('given', contract.given)
            contract.location = data.get('location', contract.location)
            contract.location2 = data.get('location2', contract.location2)
            contract.contract = data.get('contract', contract.contract)
            
            if old_status == "Rasmiylashtirilmoqda":
                selected_home_id = data.get('home')
                if selected_home_id:
                    home = get_object_or_404(Home, pk=selected_home_id)
                    contract.home = home
                    contract.home_price = Decimal(str(home.home.field)) * Decimal(str(home.home.price))
                
                contract.payment = Decimal(str(data.get('payment', contract.payment)))
                contract.term = int(data.get('term', contract.term))
                contract.pay_date = int(data.get('pay_date', contract.pay_date))
                
                contract.residual = contract.home_price - contract.payment
                if contract.term > 0:
                    contract.oylik_tolov = contract.residual / contract.term
                else:
                    contract.oylik_tolov = 0
                contract.count_month = contract.term
                contract.residu = 0

            if old_status != "Tugallangan" and new_status == "Tugallangan":
                payments = Rasrochka.objects.filter(client=contract, qoldiq__gt=0)
                for payment in payments:
                    payment.amount_paid = payment.amount
                    payment.qoldiq = 0
                    payment.pay_date = timezone.now()
                    payment.save()
                
                if contract.home and contract.home.home:
                    contract.home.home.busy = True
                    contract.home.home.save()
                contract.residual = 0
                contract.debt = False
                contract.status = new_status
                contract.save()
                return Response({"detail": "Shartnoma tugallandi va barcha to'lovlar yopildi!"}, status=status.HTTP_200_OK)
            
            if old_status != "Bekor qilingan" and new_status == "Bekor qilingan":
                if contract.home and contract.home.home:
                    contract.home.home.busy = False
                    contract.home.home.save()
                contract.residual = 0
                contract.debt = False
                contract.status = new_status
                contract.save()
                return Response({"detail": "Shartnoma bekor qilindi va xonadon bo'shatildi!"}, status=status.HTTP_200_OK)
            
            contract.status = new_status
            contract.save()
            
            serializer = self.get_serializer(contract)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        with transaction.atomic():
            if instance.home and instance.home.home:
                instance.home.home.busy = False
                instance.home.home.save()

            from main.models import ClientTrash
            ClientTrash.objects.create(
                client=instance.client,
                home=instance.home,
                passport=instance.passport,
                term=instance.term,
                payment=instance.payment,
                residual=instance.residual,
                oylik_tolov=instance.oylik_tolov,
                count_month=instance.count_month,
                status=instance.status,
                debt=instance.debt,
                created=instance.created,
            )

            Rasrochka.objects.filter(client=instance).delete()
            
            return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='payment-schedule')
    def payment_schedule(self, request, pk=None):
        contract = self.get_object()
        rasrochka = Rasrochka.objects.filter(client=contract).order_by("month")
        
        payment_schedule_data = []
        total_amount = Decimal('0')
        total_paid = Decimal('0')
        total_remaining = Decimal('0')
        
        for payment in rasrochka:
            payment_data = {
                'id': payment.id,
                'month': payment.month,
                'amount': float(payment.amount),
                'amount_paid': float(payment.amount_paid),
                'qoldiq': float(payment.qoldiq),
                'date': payment.date.strftime('%Y-%m-%d'),
                'pay_date': payment.pay_date.strftime('%Y-%m-%d') if payment.pay_date else None,
                'is_initial': payment.month == 0,
                'is_paid': payment.qoldiq == 0,
                'can_pay': payment.qoldiq > 0 and contract.status != "Tugallangan"
            }
            payment_schedule_data.append(payment_data)
            
            total_amount += payment.amount
            total_paid += payment.amount_paid
            total_remaining += payment.qoldiq
        
        months_count = len([p for p in payment_schedule_data if not p['is_initial']])
        
        contract_data = {
            'id': contract.id,
            'contract_number': contract.contract,
            'status': contract.status,
            'pay_date': contract.pay_date,
            'total_price': float(contract.home_price),
            'client_name': contract.client.full_name if contract.client else '',
            'home_info': f"{contract.home.building.name} - {contract.home.home.home_number}" if contract.home else ''
        }
        
        return Response({
            "payment_schedule": payment_schedule_data,
            "total_amount": float(total_amount),
            "total_paid": float(total_paid),
            "total_remaining": float(contract.residual),
            "months_count": months_count,
            "contract_data": contract_data
        })

    @action(detail=True, methods=['post'], url_path='process-payment')
    def process_payment(self, request, pk=None):
        contract = self.get_object()
        payment_type = request.data.get("payment_type")
        
        with transaction.atomic():
            if payment_type == "monthly":
                debt_id = request.data.get("debt_id")
                amount_to_pay = request.data.get("amount")
                
                if not debt_id or not amount_to_pay:
                    return Response({"detail": "To'lov ma'lumotlari to'liq emas"}, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    amount_to_pay = Decimal(str(amount_to_pay))
                    rasrochka_obj = get_object_or_404(Rasrochka, pk=debt_id, client=contract)
                except (ValueError, Rasrochka.DoesNotExist):
                    return Response({"detail": "Noto'g'ri to'lov IDsi yoki miqdori"}, status=status.HTTP_400_BAD_REQUEST)
                
                if rasrochka_obj.qoldiq == 0:
                    return Response({"detail": "Bu oy uchun to'lov allaqachon to'langan."}, status=status.HTTP_400_BAD_REQUEST)

                if amount_to_pay > rasrochka_obj.qoldiq:
                    return Response({"detail": "To'lov miqdori qoldiqdan oshmasligi kerak."}, status=status.HTTP_400_BAD_REQUEST)
                
                rasrochka_obj.amount_paid += amount_to_pay
                rasrochka_obj.pay_date = timezone.now()
                rasrochka_obj.qoldiq = rasrochka_obj.amount - rasrochka_obj.amount_paid
                rasrochka_obj.save()
                
                contract.residual -= amount_to_pay
                if contract.residual <= 0:
                    contract.debt = False
                    if contract.status == 'Rasmiylashtirilgan':
                        contract.status = 'Tugallangan'
                else:
                    contract.debt = True
                contract.save()
                
                return Response({"detail": "To'lov muvaffaqiyatli qabul qilindi"}, status=status.HTTP_200_OK)

            elif payment_type == "custom":
                custom_amount = request.data.get("custom_amount")
                
                if not custom_amount:
                    return Response({"detail": "To'lov miqdori kiritilmadi"}, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    custom_amount = Decimal(str(custom_amount))
                except ValueError:
                    return Response({"detail": "To'lov miqdori noto'g'ri formatda"}, status=status.HTTP_400_BAD_REQUEST)
                
                if custom_amount < 1:
                    return Response({"detail": "To'lov miqdori kamida 1 so'm bo'lishi kerak"}, status=status.HTTP_400_BAD_REQUEST)
                
                unpaid_months = Rasrochka.objects.filter(
                    client=contract, 
                    qoldiq__gt=0
                ).order_by("date")
                
                if not unpaid_months.exists():
                    return Response({"detail": "Barcha to'lovlar to'langan"}, status=status.HTTP_400_BAD_REQUEST)
                
                remaining_amount = custom_amount
                payments_made = 0
                last_month_paid = None
                
                for month_entry in unpaid_months:
                    if remaining_amount <= 0:
                        break
                    
                    amount_to_pay = min(remaining_amount, month_entry.qoldiq)
                    
                    month_entry.amount_paid += amount_to_pay
                    month_entry.pay_date = timezone.now()
                    month_entry.qoldiq = month_entry.amount - month_entry.amount_paid
                    month_entry.save()
                    
                    remaining_amount -= amount_to_pay
                    payments_made += 1
                    last_month_paid = month_entry
                
                contract.residual -= custom_amount
                if contract.residual <= 0:
                    contract.debt = False
                    if contract.status == 'Rasmiylashtirilgan':
                        contract.status = 'Tugallangan'
                else:
                    contract.debt = True
                contract.save()
                
                if payments_made > 0:
                    if last_month_paid and last_month_paid.qoldiq > 0:
                        return Response({"detail": f"To'lov muvaffaqiyatli qabul qilindi. {last_month_paid.month}-oy uchun qolgan qarz: {last_month_paid.qoldiq} so'm"}, status=status.HTTP_200_OK)
                    else:
                        return Response({"detail": "To'lov muvaffaqiyatli qabul qilindi"}, status=status.HTTP_200_OK)
                else:
                    return Response({"detail": "To'lov qabul qilinmadi"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({"detail": "Noto'g'ri to'lov turi"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='bulk-update-payments')
    def bulk_update_payments(self, request, pk=None):
        contract = self.get_object()
        changes = request.data.get('changes', [])
        
        if not changes:
            return Response({'detail': 'Hech qanday o\'zgarish topilmadi'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            updated_count = 0
            for change in changes:
                payment_id = change.get('payment_id')
                new_amount = change.get('amount')
                new_date = change.get('date')
                
                if not payment_id:
                    continue
                
                try:
                    payment = Rasrochka.objects.get(id=payment_id, client=contract)
                    
                    if new_amount is not None:
                        payment.amount = Decimal(str(new_amount))
                    
                    if new_date:
                        if isinstance(new_date, str):
                            payment.date = datetime.strptime(new_date, '%Y-%m-%d').date()
                        else:
                            payment.date = new_date
                    
                    payment.qoldiq = payment.amount - payment.amount_paid
                    payment.save()
                    updated_count += 1
                    
                except Rasrochka.DoesNotExist:
                    logger.warning(f"Payment not found: {payment_id} for contract {contract.id}")
                    continue
                except Exception as e:
                    logger.error(f"Error updating payment {payment_id}: {str(e)}")
                    return Response({'detail': f'To\'lovni yangilashda xatolik: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            total_remaining = Rasrochka.objects.filter(client=contract).aggregate(
                total=Sum('qoldiq')
            )['total'] or 0
            contract.residual = total_remaining
            contract.save()

            return Response({
                'detail': f'{updated_count} ta to\'lov yangilandi',
                'updated_count': updated_count
            }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='update-months-count')
    def update_months_count(self, request, pk=None):
        contract = self.get_object()
        new_months_count = request.data.get('months_count')
        
        if not new_months_count:
            return Response({'detail': 'Oylar soni kiritilmadi'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            new_months_count = int(new_months_count)
        except (ValueError, TypeError):
            return Response({'detail': 'Oylar soni raqam bo\'lishi kerak'}, status=status.HTTP_400_BAD_REQUEST)
        
        if new_months_count < 1 or new_months_count > 120:
            return Response({'detail': 'Oylar soni 1 dan 120 gacha bo\'lishi mumkin'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            existing_payments = Rasrochka.objects.filter(client=contract).exclude(month=0).order_by('month')
            current_months_count = existing_payments.count()
            
            if new_months_count == current_months_count:
                return Response({'detail': 'Oylar soni o\'zgarmadi'}, status=status.HTTP_200_OK)
            
            initial_payment = Rasrochka.objects.filter(client=contract, month=0).first()
            initial_amount = Decimal(str(initial_payment.amount)) if initial_payment else Decimal('0')
            
            total_price = Decimal(str(contract.home_price or 0))
            
            paid_payments = existing_payments.filter(qoldiq__lte=0)
            unpaid_payments = existing_payments.filter(qoldiq__gt=0)
            
            total_paid_amount = sum(Decimal(str(p.amount)) for p in paid_payments)
            partial_paid_amount = sum(Decimal(str(p.amount_paid)) for p in unpaid_payments)
            
            remaining_amount = total_price - initial_amount - total_paid_amount - partial_paid_amount
            if remaining_amount < 0:
                remaining_amount = Decimal('0')
            
            paid_months_count = paid_payments.count()
            
            if new_months_count < paid_months_count:
                return Response({
                    'detail': f'Yangi oylar soni ({new_months_count}) to\'langan oylar sonidan ({paid_months_count}) kam bo\'lishi mumkin emas'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            new_unpaid_months = new_months_count - paid_months_count
            
            new_monthly_payment = Decimal('0')
            if new_unpaid_months > 0 and remaining_amount > 0:
                new_monthly_payment = remaining_amount / new_unpaid_months
            
            if new_months_count > current_months_count:
                for payment in unpaid_payments:
                    payment.amount = new_monthly_payment
                    payment.qoldiq = new_monthly_payment - Decimal(str(payment.amount_paid))
                    payment.save()
                
                last_payment = existing_payments.last()
                base_date = last_payment.date if last_payment else contract.created.date()
                
                for month_num in range(current_months_count + 1, new_months_count + 1):
                    new_date = base_date + relativedelta(months=month_num - current_months_count)
                    Rasrochka.objects.create(
                        client=contract,
                        month=month_num,
                        amount=new_monthly_payment,
                        amount_paid=0,
                        qoldiq=new_monthly_payment,
                        date=new_date
                    )
            else:
                payments_to_delete = existing_payments.filter(month__gt=new_months_count)
                
                paid_payments_to_delete = payments_to_delete.filter(qoldiq__lte=0)
                if paid_payments_to_delete.exists():
                    paid_months_list = list(paid_payments_to_delete.values_list('month', flat=True))
                    return Response({
                        'detail': f'To\'langan oylarni o\'chirib bo\'lmaydi. To\'langan oylar: {", ".join(map(str, paid_months_list))}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                partial_payments_to_return = sum(
                    Decimal(str(p.amount_paid)) for p in payments_to_delete.filter(amount_paid__gt=0)
                )
                
                payments_to_delete.delete()
                
                remaining_unpaid_payments = Rasrochka.objects.filter(
                    client=contract, 
                    month__gt=0, 
                    month__lte=new_months_count,
                    qoldiq__gt=0
                ).order_by('month')
                
                updated_remaining_amount = remaining_amount + partial_payments_to_return
                
                if remaining_unpaid_payments.exists() and updated_remaining_amount > 0:
                    new_monthly_payment = updated_remaining_amount / remaining_unpaid_payments.count()
                    
                    for payment in remaining_unpaid_payments:
                        payment.amount = new_monthly_payment
                        payment.qoldiq = new_monthly_payment - Decimal(str(payment.amount_paid))
                        payment.save()
            
            total_remaining = Rasrochka.objects.filter(client=contract).aggregate(
                total=Sum('qoldiq')
            )['total'] or 0
            contract.residual = total_remaining
            contract.count_month = new_months_count
            contract.save()
        
        return Response({
            'detail': f'Oylar soni {new_months_count} ga o\'zgartirildi. To\'langan oylar saqlab qolindi.',
            'new_months_count': new_months_count
        }, status=status.HTTP_200_OK)

class RasrochkaViewSet(viewsets.ModelViewSet):
    queryset = Rasrochka.objects.all()
    serializer_class = RasrochkaSerializer
    permission_classes = [IsAuthenticated]

class ExpenseTypeViewSet(viewsets.ModelViewSet):
    queryset = ExpenseType.objects.all()
    serializer_class = ExpenseTypeSerializer
    permission_classes = [IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if Expense.objects.filter(expense_type=instance).exists():
            return Response(
                {"detail": "Bu chiqim turida chiqimlar mavjud. O'chirishdan oldin ularni boshqa turga o'tkazing."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        name = request.data.get('name')
        if not name:
            return Response({"detail": "Chiqim turi nomi kiritilmadi"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            expense_type = ExpenseType.objects.create(name=name)
            serializer = self.get_serializer(expense_type)
            return Response({"detail": "Chiqim turi muvaffaqiyatli qo'shildi", "expense_type": serializer.data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": f"Xatolik yuz berdi: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        expense_type = self.get_object()
        name = request.data.get('name')
        if not name:
            return Response({"detail": "Chiqim turi nomi kiritilmadi"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            expense_type.name = name
            expense_type.save()
            serializer = self.get_serializer(expense_type)
            return Response({"detail": "Chiqim turi muvaffaqiyatli yangilandi", "expense_type": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": f"Xatolik yuz berdi: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        expense_type_id = self.request.query_params.get('expense_type')
        building_id = self.request.query_params.get('building')
        
        if expense_type_id:
            queryset = queryset.filter(expense_type_id=expense_type_id)
        if building_id:
            queryset = queryset.filter(building_id=building_id)
        
        return queryset.order_by('-created')

    @action(detail=False, methods=['get'], url_path='summary')
    def get_summary(self, request):
        expenses = self.get_queryset()
        today = timezone.now().date()
        
        daily_total = expenses.filter(created__date=today).aggregate(Sum('amount'))['amount__sum'] or 0
        monthly_total = expenses.filter(created__month=today.month, created__year=today.year).aggregate(Sum('amount'))['amount__sum'] or 0
        total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
        
        return Response({
            'daily_total': float(daily_total),
            'monthly_total': float(monthly_total),
            'total_expenses': float(total_expenses),
        })

    def create(self, request, *args, **kwargs):
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            description = request.data.get('description')
            expense_type_id = request.data.get('expense_type')
            building_id = request.data.get('building')
            payment_type = request.data.get('payment_type')
            
            expense = Expense.objects.create(
                amount=amount,
                description=description,
                expense_type_id=expense_type_id,
                building_id=building_id if building_id else None,
                payment_type=payment_type
            )
            serializer = self.get_serializer(expense)
            return Response({"detail": "Chiqim muvaffaqiyatli qo'shildi", "expense": serializer.data}, status=status.HTTP_201_CREATED)
        except ValueError:
            return Response({"detail": "Summa noto'g'ri formatda kiritildi"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Xatolik yuz berdi: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        expense = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            description = request.data.get('description')
            expense_type_id = request.data.get('expense_type')
            building_id = request.data.get('building')
            payment_type = request.data.get('payment_type')
            
            expense.amount = amount
            expense.description = description
            expense.expense_type_id = expense_type_id
            expense.building_id = building_id if building_id else None
            expense.payment_type = payment_type
            
            expense.save()
            serializer = self.get_serializer(expense)
            return Response({"detail": "Chiqim muvaffaqiyatli yangilandi", "expense": serializer.data}, status=status.HTTP_200_OK)
        except ValueError:
            return Response({"detail": "Summa noto'g'ri formatda kiritildi"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Xatolik yuz berdi: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='export-pdf')
    def export_expenses_pdf(self, request):
        template_path = 'expenses/expenses_pdf.html' # This template needs to be accessible by DRF
        
        expenses = self.get_queryset()
        total = expenses.aggregate(total=Sum('amount'))['amount__sum'] or 0
        
        context = {
            'expenses': expenses,
            'total': total,
            'today': datetime.now()
        }
        
        from django.template.loader import get_template
        from xhtml2pdf import pisa
        from io import BytesIO

        template = get_template(template_path)
        html = template.render(context)
        
        response = FileResponse(BytesIO(html.encode("utf-8")), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="chiqimlar.pdf"'
        
        pisa_status = pisa.CreatePDF(BytesIO(html.encode("utf-8")), dest=response)
        if pisa_status.err:
            return Response({"detail": "PDF yaratishda xatolik yuz berdi"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return response

class BotUserViewSet(viewsets.ModelViewSet):
    queryset = BotUser.objects.all()
    serializer_class = BotUserSerializer
    permission_classes = [IsAuthenticated]

# --- Custom API Views for complex operations / PDF generation ---

class BuildingInformationAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        cities = City.objects.all()
        buildings = Building.objects.all()
        homes = Home.objects.all()
        clients = Client.objects.all()

        data = {
            "city": CitySerializer(cities, many=True).data,
            "building": BuildingSerializer(buildings, many=True).data,
            "home": HomeSerializer(homes, many=True, context={'request': request}).data,
            "client": []
        }
        
        for v in clients:
            if v.home:
                data["client"].append({
                    "id": v.pk,
                    "client_name": v.client.full_name if v.client else "Unknown",
                    "client_phone": v.client.phone or "",
                    "client_passport": v.passport,
                    "home": v.home.pk,
                    "building": v.home.building.pk,
                    "padez_number": v.home.home.padez_number,
                    "home_number": v.home.home.home_number,
                })
        return Response(data)

class HomeUploadAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        building_id = request.data.get('building')
        uploaded_file = request.FILES.get('file')

        if not building_id:
            return Response({"detail": "Bino tanlanmadi."}, status=status.HTTP_400_BAD_REQUEST)
        if not uploaded_file:
            return Response({"detail": "Iltimos, faylni tanlang."}, status=status.HTTP_400_BAD_REQUEST)

        building = get_object_or_404(Building, pk=building_id)
        
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_floor_plans')
        os.makedirs(temp_dir, exist_ok=True)

        successful_count = 0
        errors = []

        try:
            wb = openpyxl.load_workbook(uploaded_file)
            sheet = wb.active

            embedded_images = {}
            for image in sheet._images:
                img_col = image.anchor._from.col + 1
                img_row = image.anchor._from.row + 1
                try:
                    img_data = image._data()
                    if img_row not in embedded_images:
                        embedded_images[img_row] = {}
                    embedded_images[img_row][img_col] = img_data
                except Exception as e:
                    logger.error(f"Embedded image extract error: {e}")
                    continue

            with transaction.atomic():
                for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=False), start=2):
                    if all(cell.value is None for cell in row):
                        continue

                    try:
                        def get_cell_value(idx, default):
                            val = row[idx].value
                            return val if val is not None else default

                        narxi = get_cell_value(0, 0)
                        xona_raqami = get_cell_value(1, 0)
                        podezd = get_cell_value(2, 1)
                        qavat = get_cell_value(3, 1)
                        xonalar_soni = get_cell_value(4, 1)
                        maydoni = get_cell_value(5, 0)

                        narxi = int(narxi)
                        xona_raqami = int(xona_raqami)
                        podezd = int(podezd)
                        qavat = int(qavat)
                        xonalar_soni = int(xonalar_soni)
                        maydoni = float(str(maydoni).replace(',', '.'))

                        home_info = HomeInformation.objects.create(
                            padez_number=podezd,
                            home_number=xona_raqami,
                            home_floor=qavat,
                            xona=xonalar_soni,
                            field=maydoni,
                            price=narxi,
                            busy=False,
                        )

                        floor_plan_saved = False
                        cell_floor_plan = row[6] if len(row) > 6 else None
                        if cell_floor_plan and cell_floor_plan.value:
                            floor_plan_saved = save_image_from_cell(
                                cell_floor_plan, home_info, 'floor_plan', 
                                f"floor_plan_{podezd}_{xona_raqami}.png", 
                                row_idx
                            )
                        if not floor_plan_saved and row_idx in embedded_images and 7 in embedded_images[row_idx]:
                            try:
                                img_data = embedded_images[row_idx][7]
                                img_name = f"floor_plan_{podezd}_{xona_raqami}.png"
                                home_info.floor_plan.save(img_name, ContentFile(img_data), save=True)
                            except Exception as e:
                                logger.warning(f"Row {row_idx}: Embedded floor plan save error: {e}")

                        drawing_saved = False
                        cell_drawing = row[7] if len(row) > 7 else None
                        if cell_drawing and cell_drawing.value:
                            drawing_saved = save_image_from_cell(
                                cell_drawing, home_info, 'floor_plan_drawing', 
                                f"floor_drawing_{podezd}_{xona_raqami}.png", 
                                row_idx
                            )
                        if not drawing_saved and row_idx in embedded_images and 8 in embedded_images[row_idx]:
                            try:
                                img_data = embedded_images[row_idx][8]
                                img_name = f"floor_drawing_{podezd}_{xona_raqami}.png"
                                home_info.floor_plan_drawing.save(img_name, ContentFile(img_data), save=True)
                            except Exception as e:
                                logger.warning(f"Row {row_idx}: Embedded drawing save error: {e}")

                        home = Home.objects.create(building=building, home=home_info)
                        home_info.home_model_id = home.pk
                        home_info.save()

                        successful_count += 1

                    except (ValueError, TypeError) as e:
                        errors.append(f"Qator {row_idx}: Ma'lumot formatida xatolik: {e}")
                        logger.error(f"Row {row_idx}: Data format error: {e}")
                        continue
                    except Exception as e:
                        errors.append(f"Qator {row_idx}: Xatolik: {e}")
                        logger.error(f"Row {row_idx}: General error: {e}")
                        continue

                building.status = True
                building.save()

        except Exception as e:
            transaction.set_rollback(True)
            Home.objects.filter(building=building).delete()
            building.status = False
            building.save()
            logger.error(f"Excel file processing error: {e}")
            return Response({"detail": f"Excel faylni o'qishda xatolik: {e}", "errors": errors}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

        if errors:
            return Response({"detail": f"{successful_count} ta xonadon muvaffaqiyatli qo'shildi. Ba'zi xatolar yuz berdi.", "errors": errors}, status=status.HTTP_207_MULTI_STATUS)
        return Response({"detail": f"{successful_count} ta xonadon muvaffaqiyatli qo'shildi."}, status=status.HTTP_200_OK)

class HomeDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        filters = {}
        building_id = request.query_params.get("building")
        city_id = request.query_params.get("city")
        if city_id and city_id.isdigit():
            filters["building__city__id"] = city_id
        if building_id and building_id.isdigit():
            filters["building__id"] = building_id
        
        homes = Home.objects.filter(**filters)

        html_content = """
        <html>
            <head>
                <style>
                .title{
                    font-size: 22px;
                   text-align: center;
                   border-bottom: 1px solid black;
                          font-family: "Times New Roman", Times, serif;
                }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                    }
                    
                    th, td {
                        border: 1px solid black;
                        padding: 6px;
                        text-align: center;
                        font-size: 17px;
                        font-family: "Times New Roman", Times, serif;
                    }
                    td {
                        font-weight: 200;
                    }
                    th {
                        background-color: #f2f2f2;
                    }
                    .n{
                        width: 20%
                    }
                     .m{
                        width: 40%
                    }
                     .i{
                        width: 40%
                    }
                </style>
            </head>
            <body>
                <h2 class="title">XONADONLAR MA'LUMOTLARI</h2>
        <table>
                    <thead>
                        <tr>
                            <th class="n">N</th>
                            <th class="m">PODEZD</th>
                            <th class="i">QAVAT</th>
                            <th class="i">XONA</th>
                            <th class="i">M<sup>2</sup></th>
                            <th class="i">NARXI</th>
                            <th class="i">HOLATI</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for row in homes:
            status_text = "Band" if row.home.busy else "Bo'sh"
            html_content += f"""
                        <tr>
                            <td>{row.home.home_number}</td>
                            <td>{row.home.padez_number}</td>
                            <td>{row.home.home_floor}</td>
                            <td>{row.home.xona}</td>
                            <td>{row.home.field}</td>
                            <td>{row.home.price:,}</td>
                            <td>{status_text}</td>
                        </tr>
            """

        html_content += """
                    </tbody>
                </table>
            </body>
        </html>
        """
        from xhtml2pdf import pisa
        from io import BytesIO

        response = FileResponse(BytesIO(html_content.encode("utf-8")), content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="XONADONLAR MA\'LUMOTLARI.pdf"'

        pisa_status = pisa.CreatePDF(BytesIO(html_content.encode("utf-8")), dest=response)
        if pisa_status.err:
            return Response({"detail": "PDF yaratishda xatolik yuz berdi"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return response

class HomeDemoDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        file_path = os.path.join(settings.MEDIA_ROOT, 'xonadonlar_malumotlari_demo.xlsx')
        if os.path.exists(file_path):
            return FileResponse(open(file_path, 'rb'), as_attachment=True, filename='xonadonlar_malumotlari_demo.xlsx')
        else:
            raise Http404("Fayl topilmadi.")

class ClientDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        html_content = """
        <html>
            <head>
                <style>
                .title{
                    font-size: 22px;
                   text-align: center;
                   border-bottom: 1px solid black;
                          font-family: "Times New Roman", Times, serif;
                }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                    }
                    th, td {
                        border: 8px solid black;
                        padding: 8px;
                        text-align: center;
                        font-size: 17px;
                          font-family: "Times New Roman", Times, serif;
                    }
                    th {
                        background-color: #f2f2f2;
                    }
                    .n{
                        width: 20%
                    }
                     .m{
                        width: 40%
                    }
                     .i{
                        width: 40%
                    }
                </style>
            </head>
            <body>
                <h2 class="title">Barcha mijzolar ro'yxati</h2>
                
                
                <table>
                    <thead>
                        <tr>
                            <th class="n">N</th>
                            <th class="m">To'liq ismi</th>
                            <th class="i">Telefon raqami</th>
                            <th class="i">Qayerda eshitgan</th>
                            <th class="i">Qo'shilgan sanasi</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        s = 1
        for row in ClientInformation.objects.all():
            html_content += f"""
                        <tr>
                            
                            <td>{s}</td>
                            <td>{row.full_name}</td>
                            <td>{row.phone or ""}\n {row.phone2 or ""}</td>
                            <td>{row.heard}</td>
                            <td>{row.created.date().strftime('%d.%m.%Y')}</td>
                        </tr>
            """
            s += 1

        html_content += """
                    </tbody>
                </table>
            </body>
        </html>
        """
        from xhtml2pdf import pisa
        from io import BytesIO

        response = FileResponse(BytesIO(html_content.encode("utf-8")), content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="mijzolar royxati.pdf"'

        pisa_status = pisa.CreatePDF(BytesIO(html_content.encode("utf-8")), dest=response)
        if pisa_status.err:
            return Response({"detail": "PDF yaratishda xatolik yuz berdi"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return response

class ContractPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        contract = get_object_or_404(Client, pk=pk)
        
        if not contract.home or not contract.home.building or not contract.home.building.city:
            return Response({"detail": "Shartnoma ma'lumotlari to'liq emas."}, status=status.HTTP_400_BAD_REQUEST)
        
        month_name = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
        month = month_name[contract.created.date().month - 1]
        
        price = contract.home_price
        try:
            foiz = (contract.payment / price) * 100
            if foiz == int(foiz):
                foiz_formatted = f"{int(foiz)}"
            else:
                foiz_formatted = f"{foiz:.2f}".rstrip('0').rstrip('.')
        except (ZeroDivisionError, TypeError):
            foiz = 0
            foiz_formatted = "0"

        rasrochka = Rasrochka.objects.filter(client=contract).order_by('month')

        total_price = int(contract.home_price)
        first_payment_obj = rasrochka.filter(month=0).first()
        down_payment = int(first_payment_obj.amount_paid if first_payment_obj else 0)
        remaining_balance = int(total_price - down_payment)
        down_payment_percentage = int((down_payment / total_price) * 100) if total_price > 0 else 0

        month_names_uz = {
            1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
            7: "iyul", 8: "avgust", 9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr"
        }

        pay_list = []
        current_balance = remaining_balance
        for i in rasrochka:
            if i.month > 0:
                month_date = i.date
                payment_amount = min(int(i.amount), current_balance)
                if current_balance > 0:
                    pay_list.append({
                        "number": i.month,
                        "day": contract.pay_date or 15,
                        "month": month_names_uz[month_date.month],
                        "year": month_date.year,
                        "payment": f"{payment_amount:,}".replace(",", " "),
                        "remaining": f"{max(0, current_balance - payment_amount):,}".replace(",", " ")
                    })
                    current_balance = max(0, current_balance - payment_amount)
                else:
                    pay_list.append({
                        "number": i.month,
                        "day": contract.pay_date or 15,
                        "month": month_names_uz[month_date.month],
                        "year": month_date.year,
                        "payment": "0",
                        "remaining": "0"
                    })
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
        from io import BytesIO

        html_content = render_to_string(
            "shart.html",
            {
                "pk": contract.contract,
                "contract": contract,
                "month": month, 
                "price": price,
                "price_text": number_to_words_uz(price),
                "pay_text": number_to_words_uz(contract.payment),
                "foiz": foiz_formatted,
                "dr": qisqartirish(contract.client.full_name) if contract.client else "",
                "total_price": f"{total_price:,}".replace(",", " "),
                "down_payment": f"{down_payment:,}".replace(",", " "),
                "remaining_balance": f"{remaining_balance:,}".replace(",", " "),
                "down_payment_percentage": down_payment_percentage,
                "pay_list": pay_list,
            },
        )

        font_config = FontConfiguration()
        pdf = HTML(string=html_content, base_url=request.build_absolute_uri()).write_pdf(font_config=font_config)

        response = FileResponse(BytesIO(pdf), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="shartnoma-{pk}.pdf"'
        return response

class JadvalDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        contract = get_object_or_404(Client, pk=pk)
        rasrochka = Rasrochka.objects.filter(client=contract).order_by('month')

        total_price = int(contract.home.home.field * contract.home.home.price)
        first_payment_obj = rasrochka.filter(month=0).first()
        down_payment = int(first_payment_obj.amount_paid if first_payment_obj else 0)
        remaining_balance = int(total_price - down_payment)
        down_payment_percentage = int((down_payment / total_price) * 100) if total_price > 0 else 0

        month_names_uz = {
            1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
            7: "iyul", 8: "avgust", 9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr"
        }

        pay_list = []
        current_balance = remaining_balance
        for i in rasrochka:
            if i.month > 0:
                month_date = i.date
                payment_amount = min(int(i.amount), current_balance)
                if current_balance > 0:
                    pay_list.append({
                        "number": i.month,
                        "day": contract.pay_date or 15,
                        "month": month_names_uz[month_date.month],
                        "year": month_date.year,
                        "payment": f"{payment_amount:,}".replace(",", " "),
                        "remaining": f"{max(0, current_balance - payment_amount):,}".replace(",", " ")
                    })
                    current_balance = max(0, current_balance - payment_amount)
                else:
                    pay_list.append({
                        "number": i.month,
                        "day": contract.pay_date or 15,
                        "month": month_names_uz[month_date.month],
                        "year": month_date.year,
                        "payment": "0",
                        "remaining": "0"
                    })

        context = {
            'contract': contract,
            'total_price': f"{total_price:,}".replace(",", " "),
            'down_payment': f"{down_payment:,}".replace(",", " "),
            'remaining_balance': f"{remaining_balance:,}".replace(",", " "),
            'down_payment_percentage': down_payment_percentage,
            'pay_list': pay_list,
        }
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
        from io import BytesIO

        html_string = render_to_string('list.html', context)

        css_string = """
            @page {
                size: A4;
                margin: 1.5cm;
            }
            body {
                font-family: "Times New Roman", Times, serif;
                font-size: 10px;
                line-height: 1.2;
            }
            .title {
                font-size: 14px;
                text-align: center;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .header-info {
                margin-bottom: 10px;
            }
            .amount {
                color: red;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 10px;
            }
            th, td {
                border: 1px solid black;
                padding: 1px;
                text-align: center;
                font-size: 9px;
            }
            th {
                background-color: #f2f2f2;
            }
            .total-row {
                font-weight: bold;
            }
            .signature {
                margin-top: 15px;
            }
            .signature-line {
                display: flex;
                justify-content: space-between;
            }
        """

        font_config = FontConfiguration()
        pdf = HTML(string=html_string).write_pdf(stylesheets=[CSS(string=css_string, font_config=font_config)], font_config=font_config)

        response = FileResponse(BytesIO(pdf), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="tolov_grafigi_{pk}.pdf"'

        return response

class StatistikaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        start = datetime(2024, 10, 1)
        month_name = [
            "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
            "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
        ]

        hozirgi_oy = datetime.now().replace(day=1)
        oylar = []

        oy = start
        while oy <= hozirgi_oy:
            oylar.append(oy)
            oy = (oy + timedelta(days=32)).replace(day=1)
            
        month_list = []
        number = 1
        for oy_boshi in oylar:
            oy_oxiri = (oy_boshi + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            month = datetime.strptime(str(oy_boshi), "%Y-%m-%d %H:%M:%S").date()
            month_list.append({
                "number": number,
                "month": f"{month_name[month.month - 1]}. {month.year} - yil",
                "download_url": f"/api/statistics/download/{oy_boshi.date()}:::{oy_oxiri.date()}/",
            })
            number += 1
        return Response({"month_list": month_list})

class StatisticsDownloadAllAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        start = datetime(2024, 10, 1)
        month_name = [
            "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
            "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
        ]

        hozirgi_oy = datetime.now().replace(day=1)
        oylar = []

        oy = start
        while oy <= hozirgi_oy:
            oylar.append(oy)
            oy = (oy + timedelta(days=32)).replace(day=1)

        month_list = []
        number = 1
        for oy_boshi in oylar:
            oy_oxiri = (oy_boshi + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            contracts = Client.objects.filter(created__date__range=(oy_boshi, oy_oxiri))
            oylik_tushum = 0
            for contract_obj in contracts:
                rasrochka = Rasrochka.objects.filter(
                    client=contract_obj, date__date__range=(oy_boshi, oy_oxiri)
                )
                for i in rasrochka:
                    oylik_tushum += i.amount_paid
                    
            month = datetime.strptime(str(oy_boshi), "%Y-%m-%d %H:%M:%S").date()
            month_list.append(
                [number, f"{month_name[month.month - 1]} {month.year}-yil", oylik_tushum]
            )
            number += 1

        html_content = """
        <html>
            <head>
                <style>
                .title{
                    font-size: 22px;
                   text-align: center;
                   border-bottom: 1px solid black;
                          font-family: "Times New Roman", Times, serif;
                }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                    }
                    th, td {
                        border: 1px solid black;
                        padding: 8px;
                        text-align: center;
                        font-size: 17px;
                          font-family: "Times New Roman", Times, serif;
                    }
                    th {
                        background-color: #f2f2f2;
                    }
                    .n{
                        width: 20%
                    }
                     .m{
                        width: 40%
                    }
                     .i{
                        width: 40%
                    }
                </style>
            </head>
            <body>
                <h2 class="title">Oylik Tushum Hisoboti</h2>
                
                
                <table>
                    <thead>
                        <tr>
                            <th class="n">N</th>
                            <th class="m">Oy kesimi</th>
                            <th class="i">Tushum (so'm)</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for row in month_list:
            html_content += f"""
                        <tr>
                            <td>{row[0]}</td>
                            <td>{row[1]}</td>
                            <td>{row[2]:,}</td>
                        </tr>
            """

        html_content += """
                    </tbody>
                </table>
            </body>
        </html>
        """
        from xhtml2pdf import pisa
        from io import BytesIO

        response = FileResponse(BytesIO(html_content.encode("utf-8")), content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="oylik_tushum.pdf"'

        pisa_status = pisa.CreatePDF(BytesIO(html_content.encode("utf-8")), dest=response)
        if pisa_status.err:
            return Response({"detail": "PDF yaratishda xatolik yuz berdi"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return response

class StatisticsDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, date_range, *args, **kwargs):
        month_name = [
            "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
            "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
        ]
        action_parts = str(date_range).split(":::")
        if len(action_parts) != 2:
            return Response({"detail": "Noto'g'ri sana diapazoni formati."}, status=status.HTTP_400_BAD_REQUEST)
        
        start_date_str = action_parts[0]
        end_date_str = action_parts[1]

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"detail": "Sana formati noto'g'ri. YYYY-MM-DD formatida bo'lishi kerak."}, status=status.HTTP_400_BAD_REQUEST)

        contracts_all = Client.objects.filter(created__date__range=(start_date, end_date))
        contract_formalized = 0
        contract_cancelled = 0
        for v in contracts_all:
            if v.status in ["Rasmiylashtirilgan", "Tugallangan"]:
                contract_formalized += 1
            if v.status == "Bekor qilingan":
                contract_cancelled += 1

        clients = ClientInformation.objects.filter(
            created__date__range=(start_date, end_date)
        )
        rasrochka_payments = Rasrochka.objects.filter(date__date__range=(start_date, end_date))
        total_income = rasrochka_payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

        html_content = """
        <html>
            <head>
                <style>
                .title{
                    font-size: 22px;
                   text-align: center;
                   border-bottom: 1px solid black;
                          font-family: "Times New Roman", Times, serif;
                }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                    }
                    th, td {
                        border: 1px solid black;
                        padding: 5px;
                        text-align: center;
                        font-size: 15px;
                          font-family: "Times New Roman", Times, serif;
                    }
                    .m {
                        border: 1px solid black;
                        font-weight: bold;
                    }
                    th {
                        background-color: #f2f2f2;
                    }
                    .n{
                        width: 20%
                    }
                </style>
            </head>
            <body>
                <h2 class="title">Oylik tushum hisoboti.
        """
        html_content += f"""
         {month_name[int(str(start_date).split("-")[1]) - 1]}, {str(start_date).split("-")[0]} - yil</h2>
                
                
                <table>
                    <tbody>"""
        html_content += f"""
                        <tr>
                            <td class="m">Barcha mijozlar</td>
                            <td>{len(clients)}</td>
                        </tr>
                        <tr>
                            <td class="m">Shartnomalar</td>
                            <td>             
                                <table>
                                    <tbody>
                                        <tr> 
                                            <td class="m">Barchasi</td>
                                            <td>{len(contracts_all)}</td>
                                        </tr>
                                        <tr> 
                                            <td class="m">Rasmiylashtirilgan</td>
                                            <td>{contract_formalized}</td>
                                        </tr>
                                        <tr> 
                                            <td class="m">Bekor qilingan</td>
                                            <td>{contract_cancelled}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td class="m">Umumiy tushum</td>
                            <td>{total_income:,} so'm</td>
                        </tr>
                        """

        html_content += """
                    </tbody>
                </table>
            </body>
        </html>
        """
        from xhtml2pdf import pisa
        from io import BytesIO

        response = FileResponse(BytesIO(html_content.encode("utf-8")), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="Oylik tushum. {month_name[int(str(start_date).split("-")[1]) - 1]}, {str(start_date).split("-")[0]}.pdf"'
        )

        pisa_status = pisa.CreatePDF(BytesIO(html_content.encode("utf-8")), dest=response)
        if pisa_status.err:
            return Response({"detail": "PDF yaratishda xatolik yuz berdi"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return response

class HomePageAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        today = timezone.now().date()
        one_week_ago = today - timedelta(days=7)
        one_month_ago = today - timedelta(days=30)

        try:
            daily_expenses = Expense.objects.filter(
                created__date__gte=one_week_ago
            ).annotate(
                date=TruncDate('created')
            ).values('date').annotate(
                total=Sum('amount')
            ).order_by('date')

            expense_by_type = Expense.objects.filter(
                created__date__gte=one_month_ago
            ).values(
                'expense_type__name'
            ).annotate(
                total=Sum('amount')
            ).order_by('-total')

            building_expenses = Expense.objects.filter(
                created__date__gte=one_month_ago,
                building__isnull=False
            ).values(
                'building__name'
            ).annotate(
                total=Sum('amount')
            ).order_by('-total')

            expense_data = {
                'daily': {
                    'dates': [expense['date'].strftime('%Y-%m-%d') for expense in daily_expenses],
                    'amounts': [float(expense['total']) for expense in daily_expenses]
                },
                'by_type': {
                    'types': [expense['expense_type__name'] or 'Nomalum' for expense in expense_by_type],
                    'amounts': [float(expense['total']) for expense in expense_by_type]
                },
                'by_building': {
                    'buildings': [expense['building__name'] or 'Nomalum' for expense in building_expenses],
                    'amounts': [float(expense['total']) for expense in building_expenses]
                }
            }
        except Exception as e:
            logger.error(f"Error processing expense data for HomePage: {e}")
            expense_data = {
                'daily': {'dates': [], 'amounts': []},
                'by_type': {'types': [], 'amounts': []},
                'by_building': {'buildings': [], 'amounts': []}
            }

        sotuv = Rasrochka.objects.all()
        kunlik_tushum = sotuv.filter(
            amount_paid__gt=0,
            pay_date__date=today
        ).aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

        haftalik_tushum = sotuv.filter(
            amount_paid__gt=0,
            pay_date__date__gte=one_week_ago
        ).aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

        oylik_tushum = sotuv.filter(
            amount_paid__gt=0,
            pay_date__date__gte=one_month_ago
        ).aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

        umumiy_tushum = sotuv.filter(
            amount_paid__gt=0
        ).aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

        tushum_data = {
            "status": sotuv.exists(),
            "kunlik_tushum": float(kunlik_tushum),
            "haftalik_tushum": float(haftalik_tushum),
            "oylik_tushum": float(oylik_tushum),
            "umumiy": float(umumiy_tushum),
        }

        total_qarz = Client.objects.filter(debt=True).aggregate(total=Sum('residual'))['total'] or 0
        
        context = {
            'tushum': tushum_data,
            'client_count': ClientInformation.objects.count(),
            'building_count': Building.objects.count(),
            'month_client': ClientInformation.objects.filter(created__month=timezone.now().month).count(),
            'contract_formalized': Client.objects.filter(status='Rasmiylashtirilgan').count(),
            'contract_completed': Client.objects.filter(status='Tugallangan').count(),
            'total_debt_amount': float(total_qarz),
            'debtors': {
                'debtor_count': Client.objects.filter(debt=True).count(),
                'nodebtor_count': Client.objects.filter(debt=False).count()
            },
            'client_heard_counts': {
                'Instagramda': ClientInformation.objects.filter(heard='Instagramda').count(),
                'Telegramda': ClientInformation.objects.filter(heard='Telegramda').count(),
                'YouTubeda': ClientInformation.objects.filter(heard='YouTubeda').count(),
                'Odamlar orasida': ClientInformation.objects.filter(heard='Odamlar orasida').count(),
                'Xech qayerda': ClientInformation.objects.filter(heard='Xech qayerda').count()
            },
            'week_client_counts': [ClientInformation.objects.filter(created__date=d).count() for d in [(today - timedelta(days=x)) for x in range(6, -1, -1)]],
            'building_names': [b.name for b in Building.objects.all()],
            'building_cities': [b.city.name for b in Building.objects.all()],
            'home_occupancy_percentage': [
                round((Home.objects.filter(building=b, home__busy=True).count() / Home.objects.filter(building=b).count()) * 100) 
                if Home.objects.filter(building=b).count() > 0 else 0
                for b in Building.objects.all()
            ],
            'expense_data': expense_data
        }
        return Response(context)
