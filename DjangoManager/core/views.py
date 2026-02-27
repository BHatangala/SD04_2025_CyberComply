from django.shortcuts import render

# Create your views here.
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.db import transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import json

from .models import UserProfile

AI_API_URL = "http://127.0.0.1:5000"

@csrf_exempt
def analyze_compliance(request):
    if request.method == 'POST':
        # Get file from request
        uploaded_file = request.FILES.get('document')
        company_name = request.POST.get('company_name', '')
        department = request.POST.get('department', '')
        
        # Forward to AI service
        files = {'file': uploaded_file}
        data = {
            'company_name': company_name,
            'department': department
        }
        
        response = requests.post(
            f"{AI_API_URL}/analyze",
            files=files,
            data=data
        )
        
        return JsonResponse(response.json())
    
@csrf_exempt
def signup(request):
    """
    API endpoint for user registration.
    Creates auth_user and corresponding UserProfile.
    """

    # Only allow POST requests
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    # Parse JSON request body
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    full_name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role_ui = (payload.get("role") or "").strip()

    # Basic validation
    if not full_name or not email or not password or not role_ui:
        return JsonResponse({"detail": "All fields are required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Invalid email format"}, status=400)

    # Map frontend role text to database enum
    role_map = {
        "General user": UserProfile.Role.GENERAL,
        "Administrative user": UserProfile.Role.ADMIN,
    }

    role_db = role_map.get(role_ui)
    if not role_db:
        return JsonResponse({"detail": "Invalid role selected"}, status=400)

    # Prevent duplicate registrations
    if User.objects.filter(username=email).exists():
        return JsonResponse({"detail": "Email already registered"}, status=409)

    # Create both records atomically
    with transaction.atomic():

        # Django automatically hashes the password
        auth_user = User.objects.create_user(
            username=email,
            email=email,
            password=password
        )

        UserProfile.objects.create(
            auth_user=auth_user,
            full_name=full_name,
            role=role_db
        )

    return JsonResponse(
        {"detail": "Account created successfully"},
        status=201
    )    