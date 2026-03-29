import logging

from django.conf import settings
from django.urls import include, path
from django.conf.urls.static import static
from django.contrib import admin
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from core.views.base import health_check
from core.views.jwt import RefreshTokenView
from core.views.verify import TokenVerifyView
from users.views.login.login import LoginView
from users.urls.OtpRequest import urlpatterns as otp
from users.views.login.logout import LogoutView
logger = logging.getLogger(__name__)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("refresh/", RefreshTokenView.as_view(), name="token_refresh"),
    path("otp-requests/", include(otp)),
]

# Dynamically include each project app's urls/base.py
for app in settings.PROJECT_APPS:
    try:
        urlpatterns += [path(f"api/v1/{app}/", include(f"{app}.urls.base"))]
    except ModuleNotFoundError:
        logger.error(f"Module {app} in v1 not found, skipping.")
    try:
        urlpatterns += [path(f"api/v2/{app}/", include(f"{app}.urls_v2.base"))]
    except ModuleNotFoundError:
        logger.error(f"Module {app} in v2 not found, skipping.")
        
    try:
        urlpatterns += [path(f"api/v3/{app}/", include(f"{app}.urls_v3.base"))]
    except ModuleNotFoundError:
        logger.error(f"Module {app} in v3 not found, skipping.")
        
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
urlpatterns += [
    path("health/", health_check),
    path("", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]