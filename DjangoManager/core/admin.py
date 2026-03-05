from django.contrib import admin
from .models import Organization, Department, UserProfile, OtpVerification, LoginHistory

# DATABASE: User Management and Authentication Related Tables

admin.site.register(Organization)
admin.site.register(Department)
admin.site.register(UserProfile)
admin.site.register(OtpVerification)
admin.site.register(LoginHistory)