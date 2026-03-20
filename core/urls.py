# core/urls/base.py

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView 
# from users.views.custom import HomeView
# List all your app names here
app_urls = [
    "admin_pannel",
    "analytics",
    "events",
    "feed",
    "groups",
    "messaging",
    "notifications",
    "search",
    "stories",
    "users",
]

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),
    
    # API schema and documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

# Dynamically include each app's urls/base.py under its own prefix
urlpatterns += [path(f"api/v1/{app}/", include(f"{app}.urls.base")) for app in app_urls]

for app in app_urls:
    try:
        urlpatterns += [path(f"api/v2/{app}/", include(f"{app}.urls_v2.base"))]
    except ModuleNotFoundError:
        pass

for app in app_urls:
    try:
        urlpatterns += [path(f"api/v3/{app}/", include(f"{app}.urls_v3.base"))]
    except ModuleNotFoundError:
        pass

urlpatterns += [
    path('', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
