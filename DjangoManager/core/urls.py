from django.urls import path
from . import views

# URL patterns for core application APIs
urlpatterns = [

    path('', views.home, name='home'),  # This makes home.html show at http://127.0.0.1:8000/ai/
    path('analyze/', views.analyze_compliance, name='analyze_compliance'),

    # User registration endpoint
    path("api/signup/", views.signup, name="signup"),

    # User authentication (login) endpoint
    path("api/login/", views.login, name="login"),

    # Login 2FA OTP verification endpoint
    path("api/verify-otp/", views.verify_otp, name="verify_otp"),

    # Password reset OTP request endpoint
    path("api/request-password-reset/", views.request_password_reset, name="request_password_reset"),

    # Password reset OTP verification endpoint
    path("api/verify-reset-otp/", views.verify_reset_otp, name="verify_reset_otp"),

    # Password reset execution endpoint
    path("api/reset-password/", views.reset_password, name="reset_password"),

]