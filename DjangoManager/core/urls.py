from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),  # This makes home.html show at http://127.0.0.1:8000/ai/
    path('analyze/', views.analyze_compliance, name='analyze_compliance'),
]