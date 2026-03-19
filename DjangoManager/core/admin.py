from django.contrib import admin
<<<<<<< HEAD
from .models import Organization, Department, UserProfile, OtpVerification, LoginHistory, Document, AnalysisResult, Recommendation
=======
from .models import Organization, Department, UserProfile, OtpVerification, LoginHistory, Document, AnalysisResult, Recommendation, Report
>>>>>>> b298825 (Implemented reports table, backend API and  unit tests)

# DATABASE: User Management and Authentication Related Tables

admin.site.register(Organization)
admin.site.register(Department)
admin.site.register(UserProfile)
admin.site.register(OtpVerification)
admin.site.register(LoginHistory)
admin.site.register(Document)
<<<<<<< HEAD
admin.site.register(AnalysisResult)
admin.site.register(Recommendation)
=======

# DATABASE: Reporting Tables

admin.site.register(AnalysisResult)
admin.site.register(Recommendation)
admin.site.register(Report)
>>>>>>> b298825 (Implemented reports table, backend API and  unit tests)
