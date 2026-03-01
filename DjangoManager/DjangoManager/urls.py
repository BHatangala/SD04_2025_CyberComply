"""
URL configuration for DjangoManager project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from core.views import analyze_compliance, send_otp, verify_otp, delete_file

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/analyze/', analyze_compliance),
    path('api/send-otp/', send_otp),
    path('api/verify-otp/', verify_otp),
    path('api/delete-file/', delete_file),
]
