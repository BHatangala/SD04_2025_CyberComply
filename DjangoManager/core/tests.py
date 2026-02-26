from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

# Database Model Unit Tests.
from .models import Organization, Department, UserProfile, OtpVerification, LoginHistory

class CoreModelsTest(TestCase):
    def setUp(self):
        self.now = timezone.now()

        # Organizations
        self.org1 = Organization.objects.create(org_name="Lanka FinTech (Pvt) Ltd")
        self.org2 = Organization.objects.create(org_name="Serendib Health Systems PLC")

        # Departments
        self.dept1 = Department.objects.create(org=self.org1, dept_name="Information Technology")
        self.dept2 = Department.objects.create(org=self.org2, dept_name="Human Resources")

        # Auth Users
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

        # User Profiles
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

        # OTP Records
        self.otp1 = OtpVerification.objects.create(
            user=self.profile1,
            otp_hash="pbkdf2_sha256$600000$AbCdEf123$XyZHashValueExample1",
            purpose=OtpVerification.Purpose.LOGIN_2FA,
            expires_at=self.now + timedelta(minutes=3),
            used_at=self.now
        )

        self.otp2 = OtpVerification.objects.create(
            user=self.profile2,
            otp_hash="pbkdf2_sha256$600000$GhIjKl456$XyZHashValueExample2",
            purpose=OtpVerification.Purpose.RESET_PASSWORD,
            expires_at=self.now + timedelta(minutes=3),
            used_at=None
        )

        # Login History
        self.login1 = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.SUCCESS,
            ip_address="203.143.27.18",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        )

        self.login2 = LoginHistory.objects.create(
            user=self.profile2,
            status=LoginHistory.Status.FAILED,
            ip_address="112.134.45.201",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
        )

    # -----------------------------------------------------
    # Organization tests
    # -----------------------------------------------------

    def test_organization_create_and_count(self):
        # Organization rows should exist
        self.assertEqual(Organization.objects.count(), 2)

    def test_organization_unique_org_name(self):
        # org_name must be unique
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Organization.objects.create(org_name="Lanka FinTech (Pvt) Ltd")

    def test_organization_created_at_auto(self):
        # created_at should auto-set
        self.assertIsNotNone(self.org1.created_at)

    # -----------------------------------------------------
    # Department tests
    # -----------------------------------------------------

    def test_department_create_and_count(self):
        # Department rows should exist
        self.assertEqual(Department.objects.count(), 2)

    def test_department_unique_per_org(self):
        # Same dept in same org must fail
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Department.objects.create(org=self.org1, dept_name="Information Technology")

        # Same dept name in different org must pass
        Department.objects.create(org=self.org2, dept_name="Information Technology")
        self.assertEqual(
            Department.objects.filter(dept_name="Information Technology").count(),
            2
        )

    def test_department_fk_relationship(self):
        # Department must belong to correct organization
        self.assertEqual(self.dept1.org, self.org1)

    def test_department_created_at_auto(self):
        # created_at should auto-set
        self.assertIsNotNone(self.dept1.created_at)

    # -----------------------------------------------------
    # UserProfile tests
    # -----------------------------------------------------

    def test_userprofile_create_and_count(self):
        # UserProfile rows should exist
        self.assertEqual(UserProfile.objects.count(), 2)

    def test_userprofile_one_to_one_unique(self):
        # One auth_user can only have one profile
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProfile.objects.create(
                    auth_user=self.auth1,
                    org=self.org1,
                    full_name="Duplicate Profile"
                )

    def test_userprofile_defaults(self):
        # Default values should behave correctly
        p = self.profile2
        self.assertIn(p.role, [UserProfile.Role.ADMIN, UserProfile.Role.GENERAL])
        self.assertIsNotNone(p.is_verified)
        self.assertIsNotNone(p.otp_is_enabled)
        self.assertIsNotNone(p.failed_login_count)

    def test_userprofile_nullable_fields(self):
        # locked_until, last_login_at, deleted_at can be NULL
        p = self.profile1
        self.assertIsNone(p.locked_until)
        self.assertIsNotNone(p.last_login_at)
        self.assertIsNone(p.deleted_at)

    def test_userprofile_timestamps_auto(self):
        # created_at and updated_at should auto-set
        self.assertIsNotNone(self.profile1.created_at)
        self.assertIsNotNone(self.profile1.updated_at)

    def test_userprofile_org_set_null_on_delete(self):
        # Deleting org should set profile.org to NULL (SET_NULL)
        self.org1.delete()
        self.profile1.refresh_from_db()
        self.assertIsNone(self.profile1.org)

    # -----------------------------------------------------
    # OTP Verification tests
    # -----------------------------------------------------

    def test_otp_create_and_count(self):
        # OTP rows should exist
        self.assertEqual(OtpVerification.objects.count(), 2)

    def test_otp_fk_relationship(self):
        # OTP must belong to correct user profile
        self.assertEqual(self.otp1.user, self.profile1)

    def test_otp_used_at_nullable(self):
        # used_at can be NULL when OTP not used yet
        self.assertIsNone(self.otp2.used_at)

    def test_otp_expiry_logic(self):
        # expires_at should be in the future for a fresh OTP
        self.assertTrue(self.otp2.expires_at > self.now)

    def test_otp_created_at_auto(self):
        # created_at should auto-set
        self.assertIsNotNone(self.otp1.created_at)

    def test_otp_invalid_purpose_rejected_by_validation(self):
        # Purpose should be one of the defined choices (model validation)
        otp = OtpVerification(
            user=self.profile1,
            otp_hash="x",
            purpose="NOT_A_REAL_PURPOSE",
            expires_at=self.now + timedelta(minutes=3)
        )
        with self.assertRaises(Exception):
            otp.full_clean()

    # -----------------------------------------------------
    # LoginHistory tests
    # -----------------------------------------------------

    def test_login_history_create_and_count(self):
        # Login history rows should exist
        self.assertEqual(LoginHistory.objects.count(), 2)

    def test_login_attempt_time_auto(self):
        # attempt_time should auto-set
        self.assertIsNotNone(self.login1.attempt_time)

    def test_login_fk_relationship(self):
        # Login history must belong to correct profile
        self.assertEqual(self.login2.user, self.profile2)

    def test_login_status_choices_validation(self):
        # Status should be one of the defined choices (model validation)
        log = LoginHistory(
            user=self.profile1,
            status="NOT_VALID",
            ip_address="127.0.0.1",
            user_agent="Test"
        )
        with self.assertRaises(Exception):
            log.full_clean()

    def test_login_optional_fields(self):
        # ip_address and user_agent are allowed to be NULL
        log = LoginHistory.objects.create(
            user=self.profile1,
            status=LoginHistory.Status.SUCCESS,
            ip_address=None,
            user_agent=None
        )
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)

    # -----------------------------------------------------
    # Delete cascade behavior tests
    # -----------------------------------------------------

    def test_protect_delete_userprofile_when_audit_records_exist(self):
        # Deleting a profile should be blocked because OTP/LoginHistory must remain
        with self.assertRaises(ProtectedError):
            self.profile1.delete()

    def test_cascade_delete_org_deletes_departments(self):
        # Deleting org should delete related departments (CASCADE)
        org2_id = self.org2.org_id
        self.org2.delete()
        self.assertEqual(Department.objects.filter(org_id=org2_id).count(), 0)


