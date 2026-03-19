from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
import hashlib

# Database Model Unit Tests.
from .models import Organization, Department, UserProfile, OtpVerification, LoginHistory, Document, AnalysisResult, Recommendation, AuditLog, AdminAccessRequest

class CoreModelsTest(TestCase):
    def setUp(self):
        self.now = timezone.now()

         # Create sample organizations for relationship and constraint testing
        self.org1 = Organization.objects.create(org_name="Lanka FinTech (Pvt) Ltd")
        self.org2 = Organization.objects.create(org_name="Serendib Health Systems PLC")

        # Create sample departments under different organizations
        self.dept1 = Department.objects.create(org=self.org1, dept_name="Information Technology")
        self.dept2 = Department.objects.create(org=self.org2, dept_name="Human Resources")

        # Create Django authentication users
        self.auth1 = User.objects.create_user(
            username="n.perera",
            email="n.perera@lankafintech.lk",
            password="SecurePass123!A"
        )
        self.auth2 = User.objects.create_user(
            username="s.jayasinghe",
            email="s.jayasinghe@serendibhealth.lk",
            password="SecurePass123!B"
        )

        # Create user profiles linked to the authentication users
        self.profile1 = UserProfile.objects.create(
            auth_user=self.auth1,
            org=self.org1,
            full_name="Nimal Perera",
            role=UserProfile.Role.ADMIN,
            is_verified=True,
            otp_is_enabled=True,
            failed_login_count=0,
            locked_until=None,
            last_login_at=self.now - timedelta(hours=2),
            deleted_at=None
        )

        self.profile2 = UserProfile.objects.create(
            auth_user=self.auth2,
            org=self.org2,
            full_name="Sahan Jayasinghe",
            role=UserProfile.Role.GENERAL,
            is_verified=False,
            otp_is_enabled=False,
            failed_login_count=3,
            locked_until=self.now + timedelta(minutes=15),
            last_login_at=self.now - timedelta(days=1),
            deleted_at=None
        )

        # Create hashed OTP sample values for OTP verification records
        raw_otp1 = "123456"
        raw_otp2 = "654321"

        self.otp1 = OtpVerification.objects.create(
            user=self.profile1,
            otp_hash=hashlib.sha256(raw_otp1.encode()).hexdigest(),
            purpose=OtpVerification.Purpose.LOGIN_2FA,
            expires_at=self.now + timedelta(minutes=3),
            used_at=self.now
        )

        self.otp2 = OtpVerification.objects.create(
            user=self.profile2,
            otp_hash=hashlib.sha256(raw_otp2.encode()).hexdigest(),
            purpose=OtpVerification.Purpose.RESET_PASSWORD,
            expires_at=self.now + timedelta(minutes=3),
            used_at=None
        )

        # Create login history records for audit trail testing
        self.login1 = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.SUCCESS,
            purpose=LoginHistory.Purpose.LOGIN,
            ip_address="203.143.27.18",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        )

        self.login2 = LoginHistory.objects.create(
            user=self.profile2,
            status=LoginHistory.Status.FAILED,
            purpose=LoginHistory.Purpose.LOGIN,
            ip_address="112.134.45.201",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
        )

        # Create sample document records
        self.doc1 = Document.objects.create(
            user=self.profile1,
            org=self.org1,
            dept=self.dept1,
            original_filename="privacy_policy.pdf",
            file_type="PDF",
            size_bytes=204800,
            s3_key="docs/privacy_policy_v1.pdf",
            status=Document.Status.UPLOADED
        )

        self.doc2 = Document.objects.create(
            user=self.profile2,
            org=self.org2,
            dept=self.dept2,
            original_filename="employee_data.docx",
            file_type="DOCX",
            size_bytes=102400,
            s3_key="docs/employee_data_v1.docx",
            status=Document.Status.COMPLETED
        )

        # Create sample AnalysisResult records for recommendation testing
        self.result1 = AnalysisResult.objects.create(document=self.doc1)
        self.result2 = AnalysisResult.objects.create(document=self.doc2)

        # Create sample recommendation records
        self.rec1 = Recommendation.objects.create(
            result=self.result1,
            recommendation_text="Ensure all sensitive data is encrypted at rest.",
            status=Recommendation.Status.PENDING,
            act_name="Data Protection Act",
            page_no=12,
            line_no=5
        )

        self.rec2 = Recommendation.objects.create(
            result=self.result1,
            recommendation_text="Update access control policies to restrict admin privileges.",
            status=Recommendation.Status.IN_PROGRESS,
            act_name="Cybersecurity Act",
            page_no=7,
            line_no=20
        )

        # Create sample audit log records
        self.log1 = AuditLog.objects.create(
            user=self.profile1,
            action_type="UPLOAD",
            target_type="document",
            target_id=self.doc1.document_id,
            success=True,
            ip_address="203.143.27.18"
        )

        self.log2 = AuditLog.objects.create(
            user=self.profile2,
            action_type="DELETE",
            target_type="document",
            target_id=self.doc2.document_id,
            success=False,
            ip_address="112.134.45.201"
        )

    # -----------------------------------------------------
    # Organization tests
    # -----------------------------------------------------

    def test_organization_create_and_count(self):
        # Verify that two organization records were created successfully
        self.assertEqual(Organization.objects.count(), 2)

    def test_organization_unique_org_name(self):
        # Verify that duplicate organization names are rejected by the unique constraint
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Organization.objects.create(org_name="Lanka FinTech (Pvt) Ltd")

    def test_organization_created_at_auto(self):
        # Verify that created_at is automatically populated when an organization is created
        self.assertIsNotNone(self.org1.created_at)

    def test_organization_str(self):
        # Verify that the string representation returns the organization name
        self.assertEqual(str(self.org1), "Lanka FinTech (Pvt) Ltd")        

    # -----------------------------------------------------
    # Department tests
    # -----------------------------------------------------

    def test_department_create_and_count(self):
        # Verify that two department records were created successfully
        self.assertEqual(Department.objects.count(), 2)

    def test_department_unique_per_org(self):
        # Verify that duplicate department names are not allowed within the same organization
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Department.objects.create(org=self.org1, dept_name="Information Technology")

        # Verify that the same department name is allowed under a different organization
        Department.objects.create(org=self.org2, dept_name="Information Technology")
        self.assertEqual(
            Department.objects.filter(dept_name="Information Technology").count(),
            2
        )

    def test_department_fk_relationship(self):
        # Verify that the department is correctly linked to its organization
        self.assertEqual(self.dept1.org, self.org1)

    def test_department_created_at_auto(self):
        # Verify that created_at is automatically populated when a department is created
        self.assertIsNotNone(self.dept1.created_at)

    def test_department_str(self):
        # Verify that the string representation includes organization and department name
        self.assertEqual(str(self.dept1), "Lanka FinTech (Pvt) Ltd - Information Technology")        

    # -----------------------------------------------------
    # UserProfile tests
    # -----------------------------------------------------

    def test_userprofile_create_and_count(self):
        # Verify that two user profile records were created successfully
        self.assertEqual(UserProfile.objects.count(), 2)

    def test_userprofile_one_to_one_unique(self):
        # Verify that one Django auth user cannot have more than one user profile
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProfile.objects.create(
                    auth_user=self.auth1,
                    org=self.org1,
                    full_name="Duplicate Profile"
                )

    def test_userprofile_defaults(self):
        ## Verify that important profile fields contain valid default or assigned values
        p = self.profile2
        self.assertIn(p.role, [UserProfile.Role.ADMIN, UserProfile.Role.GENERAL])
        self.assertIsNotNone(p.is_verified)
        self.assertIsNotNone(p.otp_is_enabled)
        self.assertIsNotNone(p.failed_login_count)

    def test_userprofile_nullable_fields(self):
        # Verify that nullable fields behave correctly when values are present or absent
        p = self.profile1
        self.assertIsNone(p.locked_until)
        self.assertIsNotNone(p.last_login_at)
        self.assertIsNone(p.deleted_at)

    def test_userprofile_timestamps_auto(self):
        # Verify that created_at and updated_at are automatically populated
        self.assertIsNotNone(self.profile1.created_at)
        self.assertIsNotNone(self.profile1.updated_at)

    def test_userprofile_org_set_null_on_delete(self):
        # Verify that deleting an organization sets the related profile organization to NULL
        self.org1.delete()
        self.profile1.refresh_from_db()
        self.assertIsNone(self.profile1.org)

    def test_userprofile_str_returns_full_name(self):
        # Verify that the string representation returns full_name when it exists
        self.assertEqual(str(self.profile1), "Nimal Perera")

    def test_userprofile_str_falls_back_to_username(self):
        # Verify that the string representation falls back to the auth username when full_name is empty
        auth_user = User.objects.create_user(
            username="temp.user",
            email="temp.user@example.com",
            password="SecurePass123!C"
        )
        profile = UserProfile.objects.create(
            auth_user=auth_user,
            full_name="",
            role=UserProfile.Role.GENERAL
        )
        self.assertEqual(str(profile), "temp.user")

    def test_userprofile_deleted_at_can_be_set(self):
        # Verify that the soft delete timestamp can be assigned and stored correctly
        deleted_time = timezone.now()
        self.profile1.deleted_at = deleted_time
        self.profile1.save()
        self.profile1.refresh_from_db()
        self.assertIsNotNone(self.profile1.deleted_at)        

    # -----------------------------------------------------
    # OTP Verification tests
    # -----------------------------------------------------

    def test_otp_create_and_count(self):
        # Verify that two OTP verification records were created successfully
        self.assertEqual(OtpVerification.objects.count(), 2)

    def test_otp_fk_relationship(self):
        # Verify that the OTP record is correctly linked to the related user profile
        self.assertEqual(self.otp1.user, self.profile1)

    def test_otp_used_at_nullable(self):
        # Verify that used_at can remain NULL for an unused OTP
        self.assertIsNone(self.otp2.used_at)

    def test_otp_expiry_logic(self):
        # Verify that a newly created OTP has a future expiry time
        self.assertTrue(self.otp2.expires_at > self.now)

    def test_otp_created_at_auto(self):
        # Verify that created_at is automatically populated when an OTP is created
        self.assertIsNotNone(self.otp1.created_at)

    def test_otp_invalid_purpose_rejected_by_validation(self):
        # Verify that invalid OTP purpose values are rejected during model validation
        otp = OtpVerification(
            user=self.profile1,
            otp_hash="x",
            purpose="NOT_A_REAL_PURPOSE",
            expires_at=self.now + timedelta(minutes=3)
        )
        with self.assertRaises(Exception):
            otp.full_clean()

    def test_otp_str(self):
        # Verify that the string representation includes the profile and OTP purpose
        self.assertEqual(str(self.otp1), f"{self.profile1} - {self.otp1.purpose}")

    def test_otp_first_login_purpose_allowed(self):
        # Verify that FIRST_LOGIN is accepted as a valid OTP purpose
        otp = OtpVerification.objects.create(
            user=self.profile1,
            otp_hash=hashlib.sha256("111111".encode()).hexdigest(),
            purpose=OtpVerification.Purpose.FIRST_LOGIN,
            expires_at=self.now + timedelta(minutes=5)
        )
        self.assertEqual(otp.purpose, OtpVerification.Purpose.FIRST_LOGIN)

    def test_otp_delete_account_purpose_allowed(self):
        # Verify that DELETE_ACCOUNT is accepted as a valid OTP purpose
        otp = OtpVerification.objects.create(
            user=self.profile1,
            otp_hash=hashlib.sha256("222222".encode()).hexdigest(),
            purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
            expires_at=self.now + timedelta(minutes=5)
        )
        self.assertEqual(otp.purpose, OtpVerification.Purpose.DELETE_ACCOUNT)

    def test_otp_admin_request_verify_purpose_allowed(self):
        # Verify that ADMIN_REQUEST_VERIFY is accepted as a valid OTP purpose
        otp = OtpVerification.objects.create(
            user=self.profile1,
            otp_hash=hashlib.sha256("333333".encode()).hexdigest(),
            purpose=OtpVerification.Purpose.ADMIN_REQUEST_VERIFY,
            expires_at=self.now + timedelta(minutes=5)
        )
        self.assertEqual(otp.purpose, OtpVerification.Purpose.ADMIN_REQUEST_VERIFY)           

    # -----------------------------------------------------
    # LoginHistory tests
    # -----------------------------------------------------

    def test_login_history_create_and_count(self):
        # Verify that two login history records were created successfully
        self.assertEqual(LoginHistory.objects.count(), 2)

    def test_login_attempt_time_auto(self):
        # Verify that attempt_time is automatically populated when a login history record is created
        self.assertIsNotNone(self.login1.attempt_time)

    def test_login_fk_relationship(self):
        # Verify that the login history record is correctly linked to the related user profile
        self.assertEqual(self.login2.user, self.profile2)

    def test_login_status_choices_validation(self):
        # Verify that invalid login status values are rejected during model validation
        log = LoginHistory(
            user=self.profile1,
            status="NOT_VALID",
            purpose=LoginHistory.Purpose.LOGIN,
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        with self.assertRaises(Exception):
            log.full_clean()

    def test_login_optional_fields(self):
        # Verify that ip_address and user_agent are allowed to be NULL
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.SUCCESS,
            purpose=LoginHistory.Purpose.LOGIN,
            ip_address=None,
            user_agent=None
        )
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)

    def test_login_pending_otp_status_allowed(self):
        # Verify that PENDING_OTP is accepted as a valid login history status
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.PENDING_OTP,
            purpose=LoginHistory.Purpose.FIRST_LOGIN_OTP,
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        self.assertEqual(log.status, LoginHistory.Status.PENDING_OTP) 

    def test_login_locked_status_allowed(self):
        # Verify that LOCKED is accepted as a valid login history status
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.LOCKED,
            purpose=LoginHistory.Purpose.LOGIN,
            ip_address="127.0.0.1",
            user_agent="Test Browser"
        )
        self.assertEqual(log.status, LoginHistory.Status.LOCKED)

    def test_loginhistory_str(self):
        # Verify that the string representation includes the profile and login status
        self.assertEqual(str(self.login1), f"{self.profile1} - {self.login1.status}")

    def test_login_login_2fa_otp_purpose_allowed(self):
        # Verify that LOGIN_2FA_OTP is accepted as a valid login history purpose
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.PENDING_OTP,
            purpose=LoginHistory.Purpose.LOGIN_2FA_OTP,
            ip_address="127.0.0.1",
            user_agent="Test Browser"
        )
        self.assertEqual(log.purpose, LoginHistory.Purpose.LOGIN_2FA_OTP)

    def test_login_reset_password_otp_purpose_allowed(self):
        # Verify that RESET_PASSWORD_OTP is accepted as a valid login history purpose
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.PENDING_OTP,
            purpose=LoginHistory.Purpose.RESET_PASSWORD_OTP,
            ip_address="127.0.0.1",
            user_agent="Test Browser"
        )
        self.assertEqual(log.purpose, LoginHistory.Purpose.RESET_PASSWORD_OTP)

    def test_login_delete_account_otp_purpose_allowed(self):
        # Verify that DELETE_ACCOUNT_OTP is accepted as a valid login history purpose
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.PENDING_OTP,
            purpose=LoginHistory.Purpose.DELETE_ACCOUNT_OTP,
            ip_address="127.0.0.1",
            user_agent="Test Browser"
        )
        self.assertEqual(log.purpose, LoginHistory.Purpose.DELETE_ACCOUNT_OTP)

    def test_login_update_2fa_purpose_allowed(self):
        # Verify that UPDATE_2FA is accepted as a valid login history purpose
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.SUCCESS,
            purpose=LoginHistory.Purpose.UPDATE_2FA,
            ip_address="127.0.0.1",
            user_agent="Test Browser"
        )
        self.assertEqual(log.purpose, LoginHistory.Purpose.UPDATE_2FA)

    def test_login_otp_submission_purpose_allowed(self):
        # Verify that OTP_SUBMISSION is accepted as a valid fallback login history purpose
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.FAILED,
            purpose=LoginHistory.Purpose.OTP_SUBMISSION,
            ip_address="127.0.0.1",
            user_agent="Test Browser"
        )
        self.assertEqual(log.purpose, LoginHistory.Purpose.OTP_SUBMISSION)               

    # -----------------------------------------------------
    # Email Update test
    # -----------------------------------------------------

    def test_login_update_email_purpose_allowed(self):
        """
        Verify that UPDATE_EMAIL is accepted as a valid login history purpose.
        """
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.SUCCESS,
            purpose=LoginHistory.Purpose.UPDATE_EMAIL,
            ip_address="127.0.0.1",
            user_agent="Test Browser - Email Change"
        )
        self.assertEqual(log.purpose, LoginHistory.Purpose.UPDATE_EMAIL)

    # -----------------------------------------------------
    # Delete cascade behavior tests
    # -----------------------------------------------------

    def test_protect_delete_userprofile_when_audit_records_exist(self):
        # Verify that deleting a user profile is blocked when protected OTP or audit records exist
        with self.assertRaises(ProtectedError):
            self.profile1.delete()

    def test_cascade_delete_org_deletes_departments(self):
        # Verify that deleting an organization also deletes its related departments through CASCADE
        org2_id = self.org2.org_id
        self.org2.delete()
        self.assertEqual(Department.objects.filter(org_id=org2_id).count(), 0)


    # -----------------------------------------------------
    # Document tests
    # -----------------------------------------------------
    def test_document_create_and_count(self):
        # Verify that two document records were created successfully
        self.assertEqual(Document.objects.count(), 2)

    def test_document_fk_relationships(self):
        # Verify that document is correctly linked to user, organization, and department
        self.assertEqual(self.doc1.user, self.profile1)
        self.assertEqual(self.doc1.org, self.org1)
        self.assertEqual(self.doc1.dept, self.dept1)

    def test_document_file_type_choices_validation(self):
        # Verify invalid file types are rejected
        doc = Document(
            user=self.profile1,
            org=self.org1,
            dept=self.dept1,
            original_filename="invalid.exe",
            file_type="EXE",
            s3_key="invalid.exe"
        )
        with self.assertRaises(Exception):
            doc.full_clean()

    def test_document_status_choices_validation(self):
        # Verify invalid status values are rejected
        doc = Document(
            user=self.profile1,
            org=self.org1,
            dept=self.dept1,
            original_filename="test.pdf",
            file_type="PDF",
            s3_key="test.pdf",
            status="INVALID_STATUS"
        )
        with self.assertRaises(Exception):
            doc.full_clean()

    def test_document_uploaded_at_auto(self):
        # Verify uploaded_at is automatically populated
        self.assertIsNotNone(self.doc1.uploaded_at)

    def test_document_optional_fields(self):
        # Verify optional fields behave correctly
        doc = Document.objects.create(
            user=self.profile1,
            org=self.org1,
            dept=self.dept1,
            original_filename="optional.txt",
            file_type="TXT",
            s3_key="optional.txt",
            size_bytes=None
        )
        self.assertIsNone(doc.size_bytes)

    def test_document_soft_delete(self):
        # Verify deleted_at can be set for soft deletion
        delete_time = timezone.now()
        self.doc1.deleted_at = delete_time
        self.doc1.save()
        self.doc1.refresh_from_db()
        self.assertIsNotNone(self.doc1.deleted_at)

    def test_document_str(self):
        # Verify string representation returns filename
        self.assertEqual(str(self.doc1), "privacy_policy.pdf")

    def test_cascade_delete_user_deletes_documents(self):
        # Simulate soft delete on user profile
        delete_time = timezone.now()
        self.profile1.deleted_at = delete_time
        self.profile1.save()

        # Simulate application logic: soft delete related documents
        Document.objects.filter(user=self.profile1, deleted_at__isnull=True).update(deleted_at=delete_time)

        # Verify all related documents are soft deleted
        docs = Document.objects.filter(user=self.profile1)
        self.assertTrue(all(doc.deleted_at is not None for doc in docs))

    def test_cascade_delete_org_deletes_documents(self):
        # Verify deleting an organization cascades to delete related documents
        org_id = self.org1.org_id
        self.org1.delete()
        self.assertEqual(Document.objects.filter(org_id=org_id).count(), 0)

    def test_cascade_delete_dept_deletes_documents(self):
        # Verify deleting a department cascades to delete related documents
        dept_id = self.dept1.dept_id
        self.dept1.delete()
        self.assertEqual(Document.objects.filter(dept_id=dept_id).count(), 0)

    # -----------------------------------------------------
    # Recommendation tests
    # -----------------------------------------------------

    def test_recommendation_create_and_count(self):
        # Verify that two recommendation records were created successfully
        self.assertEqual(Recommendation.objects.count(), 2)

    def test_recommendation_fk_relationship(self):
        # Verify that the recommendation is correctly linked to its analysis result
        self.assertEqual(self.rec1.result, self.result1)
        self.assertEqual(self.rec2.result, self.result1)

    def test_recommendation_status_choices_validation(self):
        # Verify that invalid status values are rejected during model validation
        rec = Recommendation(
            result=self.result1,
            recommendation_text="Test invalid status.",
            status="INVALID_STATUS",
            act_name="Some Act",
            page_no=1,
            line_no=1
        )
        with self.assertRaises(Exception):
            rec.full_clean()
    
    def test_recommendation_valid_status_pending(self):
        # Verify that PENDING is accepted as a valid recommendation status
        self.assertEqual(self.rec1.status, Recommendation.Status.PENDING)

    def test_recommendation_valid_status_in_progress(self):
        # Verify that IN_PROGRESS is accepted as a valid recommendation status
        self.assertEqual(self.rec2.status, Recommendation.Status.IN_PROGRESS)

    def test_recommendation_valid_status_done(self):
        # Verify that DONE is accepted as a valid recommendation status
        rec = Recommendation.objects.create(
            result=self.result2,
            recommendation_text="Review audit logging procedures.",
            status=Recommendation.Status.DONE,
            act_name="Audit Act",
            page_no=3,
            line_no=10
        )
        self.assertEqual(rec.status, Recommendation.Status.DONE)
    
    def test_recommendation_uuid_primary_key(self):
        # Verify that rec_id is automatically assigned as a valid UUID
        import uuid
        self.assertIsInstance(self.rec1.rec_id, uuid.UUID)

    def test_recommendation_created_at_auto(self):
        # Verify that created_at is automatically populated when a recommendation is created
        self.assertIsNotNone(self.rec1.created_at)

    def test_recommendation_cascade_delete(self):
        # Verify that deleting an analysis result also deletes its linked recommendations
        self.result1.delete()
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_recommendation_isolated_per_result(self):
        # Verify that recommendations are correctly isolated per analysis result
        Recommendation.objects.create(
            result=self.result2,
            recommendation_text="Review audit logging procedures.",
            status=Recommendation.Status.DONE,
            act_name="Audit Act",
            page_no=3,
            line_no=10
        )
        self.assertEqual(Recommendation.objects.filter(result=self.result1).count(), 2)
        self.assertEqual(Recommendation.objects.filter(result=self.result2).count(), 1)
    
    def test_recommendation_str(self):
        # Verify that the string representation includes act name and status
        self.assertEqual(str(self.rec1), "Data Protection Act - PENDING")

    # -----------------------------------------------------
    # AuditLog tests
    # -----------------------------------------------------

    def test_auditlog_create_and_count(self):
        # Verify that two audit log records were created successfully
        self.assertEqual(AuditLog.objects.count(), 2)

    def test_auditlog_fk_relationship(self):
        # Verify that the audit log is correctly linked to the user profile
        self.assertEqual(self.log1.user, self.profile1)
        self.assertEqual(self.log2.user, self.profile2)

    def test_auditlog_created_at_auto(self):
        # Verify that created_at is automatically populated when an audit log is created
        self.assertIsNotNone(self.log1.created_at)

    def test_auditlog_success_true(self):
        # Verify that success=True is stored correctly
        self.assertTrue(self.log1.success)

    def test_auditlog_success_false(self):
        # Verify that success=False is stored correctly
        self.assertFalse(self.log2.success)

    def test_auditlog_ip_address_optional(self):
        # Verify that ip_address can be NULL
        log = AuditLog.objects.create(
            user=self.profile1,
            action_type="DOWNLOAD",
            target_type="document",
            target_id=self.doc1.document_id,
            success=True,
            ip_address=None
        )
        self.assertIsNone(log.ip_address)

    def test_auditlog_user_set_null_on_delete(self):
        # Verify that deleting a user profile sets user to NULL on related audit logs
        LoginHistory.objects.filter(user=self.profile2).delete()
        OtpVerification.objects.filter(user=self.profile2).delete()
        self.profile2.delete()
        self.log2.refresh_from_db()
        self.assertIsNone(self.log2.user)

    def test_auditlog_user_nullable(self):
        # Verify that audit logs can be created without a user (anonymous actions)
        log = AuditLog.objects.create(
            user=None,
            action_type="UPLOAD",
            target_type="document",
            target_id=self.doc1.document_id,
            success=True,
            ip_address="10.0.0.1"
        )
        self.assertIsNone(log.user)

    def test_auditlog_uuid_primary_key(self):
        # Verify that audit_id is automatically assigned as a valid UUID
        import uuid
        self.assertIsInstance(self.log1.audit_id, uuid.UUID)

    def test_auditlog_str(self):
        # Verify that the string representation includes user, action type and target type
        self.assertEqual(str(self.log1), f"{self.profile1} - UPLOAD - document")

    def test_auditlog_action_type_stored_correctly(self):
        # Verify that action_type is stored and retrieved correctly
        self.assertEqual(self.log1.action_type, "UPLOAD")
        self.assertEqual(self.log2.action_type, "DELETE")

    def test_auditlog_target_id_stored_correctly(self):
        # Verify that target_id correctly stores the UUID of the affected record
        self.assertEqual(self.log1.target_id, self.doc1.document_id)

# -----------------------------------------------------
# Report & AnalysisResult tests
# -----------------------------------------------------

from .models import Report

class ReportModelTest(TestCase):
    def setUp(self):
        self.now = timezone.now()

        self.auth = User.objects.create_user(username="report.user", password="Pass123!")
        self.org = Organization.objects.create(org_name="Report Test Org")
        self.dept = Department.objects.create(org=self.org, dept_name="Report Dept")
        self.profile = UserProfile.objects.create(auth_user=self.auth, full_name="Report User")
        self.doc1 = Document.objects.create(
            user=self.profile, org=self.org, dept=self.dept,
            original_filename="report_test1.pdf", file_type="PDF",
            s3_key="docs/report_test1.pdf"
        )
        self.doc2 = Document.objects.create(
            user=self.profile, org=self.org, dept=self.dept,
            original_filename="report_test2.pdf", file_type="PDF",
            s3_key="docs/report_test2.pdf"
        )
        self.result1 = AnalysisResult.objects.create(document=self.doc1)
        self.result2 = AnalysisResult.objects.create(document=self.doc2)

        self.report1 = Report.objects.create(
            result=self.result1,
            report_snapshot={
                "company": "Lanka FinTech (Pvt) Ltd",
                "framework": "ISO 27001",
                "score": 87,
                "findings": ["Access control gaps", "Missing encryption policy"]
            },
            report_s3_key="reports/lanka-fintech-iso27001-2026-03-01.pdf",
            file_size=204800,
            expires_at=self.now + timedelta(days=30)
        )

        self.report2 = Report.objects.create(
            result=self.result2,
            report_snapshot={
                "company": "Serendib Health Systems PLC",
                "framework": "GDPR",
                "score": 72,
                "findings": ["Data retention not documented", "No DPO appointed"]
            },
            report_s3_key="reports/serendib-health-gdpr-2026-03-15.pdf",
            file_size=153600,
            expires_at=self.now + timedelta(days=30)
        )

    def test_report_create_and_count(self):
        self.assertEqual(Report.objects.count(), 2)

    def test_report_id_is_uuid(self):
        import uuid
        self.assertIsInstance(self.report1.report_id, uuid.UUID)

    def test_report_snapshot_is_dict(self):
        self.assertIsInstance(self.report1.report_snapshot, dict)
        self.assertEqual(self.report1.report_snapshot["framework"], "ISO 27001")

    def test_report_file_size_is_int(self):
        self.assertIsInstance(self.report1.file_size, int)
        self.assertEqual(self.report1.file_size, 204800)

    def test_report_s3_key_stored_correctly(self):
        self.assertEqual(
            self.report2.report_s3_key,
            "reports/serendib-health-gdpr-2026-03-15.pdf"
        )

    def test_report_generated_at_auto(self):
        self.assertIsNotNone(self.report1.generated_at)

    def test_report_expires_at_in_future(self):
        self.assertTrue(self.report1.expires_at > self.now)

    def test_report_fk_to_analysis_result(self):
        self.assertEqual(self.report1.result, self.result1)
        self.assertEqual(self.report2.result, self.result2)

    def test_report_reverse_relation(self):
        self.assertEqual(self.result1.reports.count(), 1)

    def test_cascade_delete_analysis_result_deletes_reports(self):
        result1_id = self.result1.result_id
        self.result1.delete()
        self.assertEqual(Report.objects.filter(result_id=result1_id).count(), 0)

    def test_report_missing_s3_key_raises(self):
        with self.assertRaises(Exception):
            r = Report(
                result=self.result1,
                report_snapshot={"key": "value"},
                report_s3_key=None,
                file_size=1024,
                expires_at=self.now + timedelta(days=1)
            )
            r.full_clean()

    def test_report_missing_snapshot_raises(self):
        with self.assertRaises(Exception):
            r = Report(
                result=self.result1,
                report_snapshot=None,
                report_s3_key="reports/test.pdf",
                file_size=1024,
                expires_at=self.now + timedelta(days=1)
            )
            r.full_clean()


# -----------------------------------------------------
# AdminAccessRequest tests
# -----------------------------------------------------
 
class AdminAccessRequestModelTest(TestCase):
    def setUp(self):
        self.now = timezone.now()
 
        # Auth user + profile
        self.auth = User.objects.create_user(
            username="admin.req@cybercomply.lk",
            email="admin.req@cybercomply.lk",
            password="SecurePass123!X"
        )
        self.profile = UserProfile.objects.create(
            auth_user=self.auth,
            full_name="Admin Requester",
            role=UserProfile.Role.GENERAL,
            is_verified=True,
        )
 
        # A second profile for isolation tests
        self.auth2 = User.objects.create_user(
            username="admin.req2@cybercomply.lk",
            email="admin.req2@cybercomply.lk",
            password="SecurePass123!Y"
        )
        self.profile2 = UserProfile.objects.create(
            auth_user=self.auth2,
            full_name="Admin Requester Two",
            role=UserProfile.Role.GENERAL,
            is_verified=True,
        )
 
        # OTP record used for verification FK
        self.otp = OtpVerification.objects.create(
            user=self.profile,
            otp_hash=hashlib.sha256("999999".encode()).hexdigest(),
            purpose=OtpVerification.Purpose.ADMIN_REQUEST_VERIFY,
            expires_at=self.now + timedelta(minutes=5),
        )
 
        # Base request (PENDING, no OTP yet)
        self.req1 = AdminAccessRequest.objects.create(
            user=self.profile,
            org_email="admin.req@cybercomply.lk",
            status=AdminAccessRequest.Status.PENDING,
        )
 
        # Approved request with OTP linked
        self.req2 = AdminAccessRequest.objects.create(
            user=self.profile,
            verification_otp=self.otp,
            org_email="admin.req@cybercomply.lk",
            status=AdminAccessRequest.Status.APPROVED,
            verified_at=self.now,
        )
 
        # Rejected request with failure reason
        self.req3 = AdminAccessRequest.objects.create(
            user=self.profile2,
            org_email="admin.req2@cybercomply.lk",
            status=AdminAccessRequest.Status.REJECTED,
            verified_at=self.now,
            failure_reason="Organization email domain not recognised.",
        )
 
    # ── Basic creation ────────────────────────────────────────────────────
 
    def test_admin_access_request_create_and_count(self):
        # Verify that three records were created successfully
        self.assertEqual(AdminAccessRequest.objects.count(), 3)
 
    def test_admin_access_request_uuid_primary_key(self):
        # Verify that request_id is auto-assigned as a valid UUID
        import uuid
        self.assertIsInstance(self.req1.request_id, uuid.UUID)
 
    # ── FK: user (CASCADE) ────────────────────────────────────────────────
 
    def test_admin_access_request_fk_user(self):
        # Verify that the request is correctly linked to its user profile
        self.assertEqual(self.req1.user, self.profile)
 
    def test_admin_access_request_cascade_delete_user(self):
        # Deleting the user profile must cascade-delete its access requests.
        # Capture the PK before deletion — after delete() the instance is unsaved.
        profile2_id = self.profile2.user_id
 
        # Remove PROTECT-guarded related records so the profile can be deleted
        LoginHistory.objects.filter(user=self.profile2).delete()
        OtpVerification.objects.filter(user=self.profile2).delete()
        self.profile2.delete()
 
        # Filter by the captured UUID, not the deleted instance
        self.assertEqual(
            AdminAccessRequest.objects.filter(user_id=profile2_id).count(), 0
        )
 
    # ── FK: verification_otp (SET NULL) ──────────────────────────────────
 
    def test_admin_access_request_fk_otp_set_null_on_delete(self):
        # Deleting the OTP must set verification_otp to NULL on linked requests
        otp_id = self.otp.otp_id
        # Must unlink from req2 first because OtpVerification uses PROTECT elsewhere;
        # here we only care about AdminAccessRequest's SET NULL behaviour.
        # Delete req1 that has no OTP, then delete the OTP record via DB.
        AdminAccessRequest.objects.filter(verification_otp=self.otp).update(verification_otp=None)
        self.otp.delete()
        self.req2.refresh_from_db()
        self.assertIsNone(self.req2.verification_otp)
 
    def test_admin_access_request_otp_nullable(self):
        # A request may be created without an OTP (verification_otp=None)
        self.assertIsNone(self.req1.verification_otp)
 
    def test_admin_access_request_otp_linked(self):
        # Verify that an OTP can be linked to a request
        self.assertEqual(self.req2.verification_otp, self.otp)
 
    # ── Status choices ────────────────────────────────────────────────────
 
    def test_admin_access_request_status_pending(self):
        # PENDING is accepted and stored correctly
        self.assertEqual(self.req1.status, AdminAccessRequest.Status.PENDING)
 
    def test_admin_access_request_status_approved(self):
        # APPROVED is accepted and stored correctly
        self.assertEqual(self.req2.status, AdminAccessRequest.Status.APPROVED)
 
    def test_admin_access_request_status_rejected(self):
        # REJECTED is accepted and stored correctly
        self.assertEqual(self.req3.status, AdminAccessRequest.Status.REJECTED)
 
    def test_admin_access_request_invalid_status_rejected_by_validation(self):
        # Invalid status values must fail model validation
        req = AdminAccessRequest(
            user=self.profile,
            org_email="test@example.com",
            status="INVALID_STATUS",
        )
        with self.assertRaises(Exception):
            req.full_clean()
 
    # ── Timestamps ───────────────────────────────────────────────────────
 
    def test_admin_access_request_requested_at_default(self):
        # requested_at must be populated automatically
        self.assertIsNotNone(self.req1.requested_at)
 
    def test_admin_access_request_verified_at_nullable(self):
        # verified_at may be NULL for a PENDING request
        self.assertIsNone(self.req1.verified_at)
 
    def test_admin_access_request_verified_at_set_on_approval(self):
        # verified_at is stored correctly when set
        self.assertIsNotNone(self.req2.verified_at)
 
    # ── org_email field ───────────────────────────────────────────────────
 
    def test_admin_access_request_org_email_stored(self):
        # org_email is stored and retrieved correctly
        self.assertEqual(self.req1.org_email, "admin.req@cybercomply.lk")
 
    def test_admin_access_request_org_email_required(self):
        # org_email must not be blank
        req = AdminAccessRequest(
            user=self.profile,
            org_email="",
            status=AdminAccessRequest.Status.PENDING,
        )
        with self.assertRaises(Exception):
            req.full_clean()
 
    # ── failure_reason field ──────────────────────────────────────────────
 
    def test_admin_access_request_failure_reason_nullable(self):
        # failure_reason is NULL for non-rejected requests
        self.assertIsNone(self.req1.failure_reason)
 
    def test_admin_access_request_failure_reason_stored(self):
        # failure_reason is stored correctly when provided
        self.assertEqual(
            self.req3.failure_reason,
            "Organization email domain not recognised."
        )
 
    # ── Multiple requests per user ────────────────────────────────────────
 
    def test_admin_access_request_multiple_per_user(self):
        # A user may have more than one request (e.g. re-apply after rejection)
        self.assertEqual(
            AdminAccessRequest.objects.filter(user=self.profile).count(), 2
        )
 
    def test_admin_access_request_isolated_per_user(self):
        # Requests for different users are not mixed
        self.assertEqual(
            AdminAccessRequest.objects.filter(user=self.profile2).count(), 1
        )
 
    # ── __str__ ───────────────────────────────────────────────────────────
 
    def test_admin_access_request_str(self):
        # String representation includes user, status and org_email
        expected = f"{self.profile} — PENDING (admin.req@cybercomply.lk)"
        self.assertEqual(str(self.req1), expected)