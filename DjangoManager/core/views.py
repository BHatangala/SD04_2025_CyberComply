from django.shortcuts import render

# Create your views here.
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.mail import send_mail
import json
import socket
import tempfile
import os
import boto3
import random
from botocore.exceptions import BotoCoreError, ClientError

AI_API_URL = "http://127.0.0.1:5000"

# Temporary in-memory OTP stor (replace with database later)
otp_store = {}

# Reject password-protected files
def is_password_protected(file_path, file_name):
    try:
        ext = file_name.lower().split('.')[-1]
        
        if ext == 'pdf':
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                return reader.is_encrypted
        
        elif ext == 'docx':
            import docx
            try:
                docx.Document(file_path)
                return False  # Opens fine — not protected
            except Exception:
                return True  # Failed to open — protected
        
        return False  # txt files can't be password protected
    
    except Exception:
        return False

# ClamAV Scan
def scan_file(file_path):
    try:
        cd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cd.connect((settings.CLAMAV_HOST, settings.CLAMAV_PORT))
        
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        cd.send(b'zINSTREAM\0')
        size = len(file_data)
        cd.send(size.to_bytes(4, byteorder='big'))
        cd.send(file_data)
        cd.send((0).to_bytes(4, byteorder='big'))
        
        result = cd.recv(1024).decode()
        cd.close()
        
        if 'OK' in result:
            return None #Clean
        else:
            return result #Threat detected
            
    except Exception as e:
        return str(e)

# S3 Upload
def upload_to_s3(file_path, file_name):
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        s3.upload_file(file_path, bucket_name, file_name)
        
        # Return the S3 URL of the uploaded file
        s3_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
        return s3_url
    
    except (BotoCoreError, ClientError) as e:
        return None

@csrf_exempt
def analyze_compliance(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    uploaded_file = request.FILES.get('document')
    company_name = request.POST.get('company_name', '')
    department = request.POST.get('department', '')

    if not uploaded_file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # Step 1 — Save file temporarily
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_path = temp_file.name

    try:
        # Step 2 — Check if password protected
        if is_password_protected(temp_path, uploaded_file.name):
            return JsonResponse(
                {'error': 'File rejected — password protected files are not allowed'},
                status=400
            )

        # Step 3 — Scan for malware
        scan_result = scan_file(temp_path)
        if scan_result is not None:
            return JsonResponse(
                {
                    'error': 'File rejected — malware detected',
                    'detail': scan_result
                },
                status=400
            )

        # Step 4 — Upload clean file to S3
        s3_url = upload_to_s3(temp_path, uploaded_file.name)
        if s3_url is None:
            return JsonResponse(
                {'error': 'Failed to upload file to S3'},
                status=500
            )

        # Forward to AI service
        #files = {'file': uploaded_file}
        #data = {
            #'company_name': company_name,
            #'department': department
        #}
        
        #response = requests.post(
            #f"{AI_API_URL}/analyze",
            #files=files,
            #data=data
        #)

        #return JsonResponse(response.json())
        return JsonResponse({'status': 'success', 's3_url': s3_url})

    finally:
        # Step 5 — ALWAYS clean up temp file
        if os.path.exists(temp_path):
            os.unlink(temp_path)

# Send OTP
@csrf_exempt
def send_otp(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not email:
        return JsonResponse({'error': 'Email is required'}, status=400)
    
    # Generate OTP
    otp = random.randint(100000, 999999)
    # Store OTP temporarily
    otp_store[email] = otp

    #Send via SES
    try:
        send_mail(
            subject='Your CyberComply Verification Code',
            message=f'Your OTP verification code is: {otp}\n\nThis code is valid for 10 minutes.\n\nIf you did not request this, please ignore this email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
        return JsonResponse({'status': 'OTP sent successfully'})

    except Exception as e:
        return JsonResponse({'error': f'Failed to send OTP: {str(e)}'}, status=500)
    
# Verify OTP
@csrf_exempt
def verify_otp(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        otp_entered = data.get('otp', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not email or not otp_entered:
        return JsonResponse({'error': 'Email and OTP are required'}, status=400)

    stored_otp = otp_store.get(email)

    if stored_otp is None:
        return JsonResponse({'error': 'OTP not found. Please request a new one.'}, status=400)
    
    if int(otp_entered) == stored_otp:
        del otp_store[email]  # Remove after successful verification
        return JsonResponse({'status': 'OTP verified successfully'})
    else:
        return JsonResponse({'error': 'Invalid OTP. Please try again.'}, status=400)
    
    
# Delete file(s) from S3 — accepts single file_name or list of file_names
@csrf_exempt
def delete_file(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Accept either a single file_name or a list of file_names
    file_name = data.get('file_name', '').strip()
    file_names = data.get('file_names', [])

    # Combine into one list
    if file_name:
        file_names.append(file_name)

    if not file_names:
        return JsonResponse({'error': 'No file names provided'}, status=400)

    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        objects = [{'Key': name} for name in file_names]
        s3.delete_objects(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Delete={'Objects': objects}
        )
        return JsonResponse({'status': f'{len(file_names)} file(s) deleted from S3'})

    except (BotoCoreError, ClientError) as e:
        return JsonResponse({'error': f'Failed to delete file(s): {str(e)}'}, status=500)