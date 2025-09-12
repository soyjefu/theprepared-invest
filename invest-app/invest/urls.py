# invest-app/invest/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # trading 앱의 URL을 포함시킵니다.
    path('', include('trading.urls')),
]