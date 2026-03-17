from django.contrib import admin
from .models import Organization, Department, UserProfile, OtpVerification, LoginHistory, Document

# DATABASE: User Management and Authentication Related Tables

admin.site.register(Organization)
admin.site.register(Department)
admin.site.register(UserProfile)
admin.site.register(OtpVerification)
admin.site.register(LoginHistory)
admin.site.register(Document)