from django.contrib import admin
from .models import Organization, Department, UserProfile, OtpVerification, LoginHistory, Document, AnalysisResult, Recommendation, Report, AuditLog, AdminAccessRequest, ReportDownload

# DATABASE: User Management and Authentication Related Tables

admin.site.register(Organization)
admin.site.register(Department)
admin.site.register(UserProfile)
admin.site.register(OtpVerification)
admin.site.register(LoginHistory)
admin.site.register(AuditLog)
admin.site.register(Document)
admin.site.register(AdminAccessRequest)

# DATABASE: Reporting Tables

admin.site.register(AnalysisResult)
admin.site.register(Recommendation)
admin.site.register(Report)
admin.site.register(ReportDownload)
