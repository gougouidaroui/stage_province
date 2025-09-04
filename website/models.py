from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from decimal import Decimal
import uuid

class User(AbstractUser):
    """Extended user model for citizens and staff"""
    USER_TYPES = [
        ('citizen', 'Citizen'),
        ('data_entry_staff', 'Data Entry Staff'),
        ('investigator', 'Investigator'),
        ('supervisor', 'Supervisor'),
        ('admin', 'Admin'),
    ]
    
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='citizen')
    national_id = models.CharField(max_length=20, unique=True)
    phone_validator = RegexValidator(regex=r'^\+212[0-9]{9}$', message="Phone number must be in format: '+212xxxxxxxxx'")
    phone_number = models.CharField(validators=[phone_validator], max_length=17, unique=True)
    birth_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=6, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Override groups and user_permissions to avoid reverse accessor clash
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='website_user_groups',  # Unique related_name
        help_text='The groups this user belongs to.',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='website_user_permissions',  # Unique related_name
        help_text='Specific permissions for this user.',
    )


class SocialIndicatorThreshold(models.Model):
    """Configuration for AMO and Social Aid thresholds"""
    PROGRAM_TYPES = [
        ('amo', 'AMO Health Insurance'),
        ('social_aid', 'Social Aid'),
    ]
    
    program_type = models.CharField(max_length=20, choices=PROGRAM_TYPES)
    max_score = models.DecimalField(max_digits=10, decimal_places=4)
    effective_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['program_type', 'effective_date']

class PossessionCategory(models.Model):
    """Categories of possessions that affect social indicator"""
    name = models.CharField(max_length=100)  # e.g., "Vehicles", "Real Estate", "Electronics"
    description = models.TextField()
    is_active = models.BooleanField(default=True)

class PossessionType(models.Model):
    """Specific types of possessions with their point values"""
    category = models.ForeignKey(PossessionCategory, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g., "Normal Car", "Luxury Car", "Motorcycle"
    description = models.TextField()
    point_value = models.DecimalField(max_digits=10, decimal_places=4)  # e.g., 0.14 for normal car
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class CitizenProfile(models.Model):
    """Extended profile information for citizens"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    family_size = models.IntegerField(default=1)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    has_other_insurance = models.BooleanField(default=False)
    other_insurance_details = models.TextField(blank=True)
    current_social_indicator = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    last_calculated = models.DateTimeField(null=True, blank=True)
    
class CitizenPossession(models.Model):
    """Possessions owned by citizens"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('under_investigation', 'Under Investigation'),
        ('disputed', 'Disputed'),
        ('removed', 'Removed'),
    ]
    
    citizen = models.ForeignKey(User, on_delete=models.CASCADE)
    possession_type = models.ForeignKey(PossessionType, on_delete=models.CASCADE)
    description = models.TextField()  # Additional details about the possession
    acquisition_date = models.DateField()
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='added_possessions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Reclamation(models.Model):
    """Citizen reclamations for possession disputes"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('under_investigation', 'Under Investigation'),
        ('approved', 'Approved - Possession Removed'),
        ('rejected', 'Rejected - Fine Applied'),
        ('closed', 'Closed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    citizen = models.ForeignKey(User, on_delete=models.CASCADE)
    possession = models.ForeignKey(CitizenPossession, on_delete=models.CASCADE)
    reason = models.TextField()  # Why citizen disputes this possession
    evidence_description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_investigator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='investigations')
    investigation_notes = models.TextField(blank=True)
    resolution_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Fine(models.Model):
    """Fines applied for false reclamations"""
    reclamation = models.OneToOneField(Reclamation, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    applied_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_paid = models.BooleanField(default=False)
    payment_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Application(models.Model):
    """Applications for AMO or Social Aid"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    PROGRAM_TYPES = [
        ('amo', 'AMO Health Insurance'),
        ('social_aid', 'Social Aid'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    citizen = models.ForeignKey(User, on_delete=models.CASCADE)
    program_type = models.CharField(max_length=20, choices=PROGRAM_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    social_indicator_at_submission = models.DecimalField(max_digits=10, decimal_places=4)
    threshold_at_submission = models.DecimalField(max_digits=10, decimal_places=4)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_applications')
    review_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class SocialIndicatorCalculation(models.Model):
    """Historical record of social indicator calculations"""
    citizen = models.ForeignKey(User, on_delete=models.CASCADE)
    total_score = models.DecimalField(max_digits=10, decimal_places=4)
    calculation_date = models.DateTimeField(auto_now_add=True)
    calculated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calculations_made')
    notes = models.TextField(blank=True)

class CalculationItem(models.Model):
    """Individual items in a social indicator calculation"""
    calculation = models.ForeignKey(SocialIndicatorCalculation, on_delete=models.CASCADE, related_name='items')
    possession = models.ForeignKey(CitizenPossession, on_delete=models.CASCADE)
    possession_name = models.CharField(max_length=200)  # Snapshot of possession name
    point_value = models.DecimalField(max_digits=10, decimal_places=4)  # Snapshot of point value
    
class AuditLog(models.Model):
    """Comprehensive audit trail for all system actions"""
    ACTION_TYPES = [
        ('user_login', 'User Login'),
        ('possession_added', 'Possession Added'),
        ('possession_updated', 'Possession Updated'),
        ('reclamation_created', 'Reclamation Created'),
        ('reclamation_investigated', 'Reclamation Investigated'),
        ('fine_applied', 'Fine Applied'),
        ('application_submitted', 'Application Submitted'),
        ('application_reviewed', 'Application Reviewed'),
        ('calculation_performed', 'Social Indicator Calculated'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    related_citizen = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs_about')
    metadata = models.JSONField(default=dict)  # Store additional context
    timestamp = models.DateTimeField(auto_now_add=True)
