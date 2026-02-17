from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

AI_API_URL = "http://127.0.0.1:5000/api"  # Change this if your Flask server runs on a different address or port

# 1. New view to display your home.html from the frontend folder
def home(request):
    return render(request, 'home.html')

# 2. Your existing logic to communicate with the Flask AI
@csrf_exempt
def analyze_compliance(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('document')
        company_name = request.POST.get('company_name', '')
        department = request.POST.get('department', '')
        
        files = {'file': uploaded_file}
        data = {
            'company_name': company_name,
            'department': department
        }
        
        try:
            response = requests.post(
                f"{AI_API_URL}/analyze",
                files=files,
                data=data
            )
            return JsonResponse(response.json())
        except requests.exceptions.ConnectionError:
            return JsonResponse({"error": "AI Server is not running. Please start api_server.py"}, status=503)
    
    return JsonResponse({"error": "Only POST requests allowed for analysis"}, status=405)