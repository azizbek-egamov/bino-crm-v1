from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    CityViewSet, BuildingViewSet, HomeInformationViewSet, HomeViewSet,
    ClientInformationViewSet, ClientViewSet, RasrochkaViewSet,
    ExpenseTypeViewSet, ExpenseViewSet, BotUserViewSet,
    BuildingInformationAPIView, HomeUploadAPIView, HomeDownloadAPIView,
    HomeDemoDownloadAPIView, ClientDownloadAPIView, ContractPDFView,
    JadvalDownloadAPIView, StatistikaAPIView, StatisticsDownloadAllAPIView,
    StatisticsDownloadAPIView, HomePageAPIView
)

from django.urls import path, include
from rest_framework import permissions
from rest_framework.routers import DefaultRouter
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

router = DefaultRouter()
router.register(r'cities', CityViewSet)
router.register(r'buildings', BuildingViewSet)
router.register(r'home-info', HomeInformationViewSet)
router.register(r'homes', HomeViewSet)
router.register(r'client-info', ClientInformationViewSet)
router.register(r'clients', ClientViewSet)
router.register(r'rasrochka', RasrochkaViewSet)
router.register(r'expense-types', ExpenseTypeViewSet)
router.register(r'expenses', ExpenseViewSet)
router.register(r'bot-users', BotUserViewSet)

schema_view = get_schema_view(
    openapi.Info(
        title="Qurilish API",
        default_version='v1',
        contact=openapi.Contact(email="azizegamov64@gmail.com"),
        license=openapi.License(name="Ardent Soft"),
    ),
    public=True,
    permission_classes=(permissions.IsAuthenticatedOrReadOnly,),
)

urlpatterns = [
    # JWT Authentication Endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Django REST Framework browsable API login/logout URLs
    path('auth/', include('rest_framework.urls', namespace='rest_framework')),

    # Custom API Views
    path('dashboard/', HomePageAPIView.as_view(), name='api_home_page'),
    path('building-information/', BuildingInformationAPIView.as_view(), name='building_information_api'),
    path('home-upload/', HomeUploadAPIView.as_view(), name='home_upload_api'),
    path('home-download/', HomeDownloadAPIView.as_view(), name='home_download_api'),
    path('home-download-template/', HomeDemoDownloadAPIView.as_view(), name='home_demo_download_api'),
    path('client-export/', ClientDownloadAPIView.as_view(), name='client_export_api'),
    path('contract-pdf/<int:pk>/', ContractPDFView.as_view(), name='contract_pdf_api'),
    path('jadval-download/<int:pk>/', JadvalDownloadAPIView.as_view(), name='jadval_download_api'),
    path('statistics/', StatistikaAPIView.as_view(), name='statistika_api'),
    path('statistics/download-all/', StatisticsDownloadAllAPIView.as_view(), name='statistika_download_all_api'),
    path('statistics/download/<str:date_range>/', StatisticsDownloadAPIView.as_view(), name='statistika_download_date_api'),

    path('', include(router.urls)),

    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),

    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    path('schema.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('schema.yaml', schema_view.without_ui(cache_timeout=0), name='schema-yaml'),
]
