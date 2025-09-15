from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from website.models import User, CitizenProfile, SocialIndicatorThreshold, PossessionCategory, PossessionType, CitizenPossession, Reclamation, Fine, Application, SocialIndicatorCalculation, CalculationItem, AuditLog
from django import forms
import logging

logger = logging.getLogger(__name__)

# Custom forms for User
class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'national_id', 'phone_number', 'user_type', 'birth_date', 'address', 'email', 'is_active', 'is_staff', 'is_superuser')

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ('username', 'national_id', 'phone_number', 'user_type', 'birth_date', 'address', 'email', 'is_active', 'is_staff', 'is_superuser')

# Inline for CitizenProfile
class CitizenProfileInline(admin.StackedInline):
    model = CitizenProfile
    can_delete = False
    verbose_name_plural = 'Citizen Profiles'
    fields = ['family_size', 'monthly_income', 'has_other_insurance', 'other_insurance_details', 'current_social_indicator', 'last_calculated']
    
    def get_formset(self, request, obj=None, **kwargs):
        if obj and obj.user_type != 'citizen':
            self.extra = 0
            self.max_num = 0
        else:
            self.extra = 1
            self.max_num = 1
        return super().get_formset(request, obj, **kwargs)

# Custom UserAdmin
class CustomUserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    inlines = [CitizenProfileInline]
    list_display = ('username', 'national_id', 'phone_number', 'user_type', 'is_verified', 'is_active')
    list_filter = ('user_type', 'is_verified', 'is_active')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('national_id', 'phone_number', 'user_type', 'birth_date', 'address', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Verification', {'fields': ('is_verified', 'verification_code')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'national_id', 'phone_number', 'user_type', 'birth_date', 'address', 'email', 'password1', 'password2', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )
    search_fields = ('username', 'national_id', 'phone_number', 'email')
    ordering = ('username',)

    def save_model(self, request, obj, form, change):
        logger.info(f"Saving User: {obj.username}, user_type: {obj.user_type}, change: {change}, pk: {obj.pk}")
        super().save_model(request, obj, form, change)
        logger.info(f"User saved: {obj.username}, pk: {obj.pk}")

    def save_formset(self, request, form, formset, change):
        logger.info(f"Saving formset for User: {form.instance.username}, formset model: {formset.model.__name__}, user pk: {form.instance.pk}")
        if formset.model == CitizenProfile and form.instance.user_type == 'citizen':
            instances = formset.save(commit=False)
            for instance in instances:
                instance.user = form.instance
                logger.info(f"Saving CitizenProfile for {form.instance.username}, user pk: {form.instance.pk}")
                instance.save()
            formset.save_m2m()
        else:
            super().save_formset(request, form, formset, change)

# Register models
admin.site.register(User, CustomUserAdmin)
admin.site.register(SocialIndicatorThreshold)
admin.site.register(PossessionCategory)
admin.site.register(PossessionType)
admin.site.register(CitizenPossession)
admin.site.register(Reclamation)
admin.site.register(Fine)
admin.site.register(Application)
admin.site.register(SocialIndicatorCalculation)
admin.site.register(CalculationItem)
admin.site.register(AuditLog)
