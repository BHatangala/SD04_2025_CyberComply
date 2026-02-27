from django.shortcuts import render

# Create your views here.
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

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