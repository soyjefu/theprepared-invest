# invest-app/invest/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Admin site URL
    path('admin/', admin.site.urls),

    # Include all URLs from the 'trading' app
    path('', include('trading.urls')),
]