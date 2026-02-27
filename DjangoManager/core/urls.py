from django.urls import path
from . import views

# URL patterns for core application APIs
urlpatterns = [

    # User registration endpoint
    path("api/signup/", views.signup, name="signup"),

    # User authentication (login) endpoint
    path("api/login/", views.login, name="login"),

]