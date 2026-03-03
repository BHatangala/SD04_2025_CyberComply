from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, StreamingHttpResponse
import json, time

AI_API_URL = "http://127.0.0.1:5000/api"  # Change this if your Flask server runs on a different address or port

# 1. New view to display your home.html from the frontend folder
def home(request):
    return render(request, 'home.html')

# 2. Your existing logic to communicate with the Flask AI
@csrf_exempt
def analyze_compliance(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)

    uploaded_file = request.FILES.get('document')
    company_name = request.POST.get('company_name', '')
    department = request.POST.get('department', '')

    def event_stream():
        # Stage 1: Django has received the file
        yield f"data: {json.dumps({'status': 'uploaded'})}\n\n".encode('utf-8')
        time.sleep(2)

        # Stage 2: Forward to Flask AI server
        try:
            files = {'file': (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)}
            data = {'company_name': company_name, 'department': department}

            # Stage 3: Request is now with the AI — notify frontend
            yield f"data: {json.dumps({'status': 'analysing'})}\n\n".encode('utf-8')

            response = requests.post(
                f"{AI_API_URL}/analyze",
                files=files,
                data=data,
                timeout=300  # 5 min timeout for large docs
            )
            result = response.json()

            # Stage 4: AI finished — send full result
            yield f"data: {json.dumps({'status': 'analysed', 'result': result})}\n\n".encode('utf-8')

        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'status': 'error', 'message': 'AI Server is not running.'})}\n\n".encode('utf-8')
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n".encode('utf-8')

    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Disables Nginx buffering if used
        }
    )