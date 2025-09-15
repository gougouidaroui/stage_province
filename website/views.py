from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.db.models import Sum, Q
from django.utils import timezone
from decimal import Decimal
from .models import *
import random
import string

def is_citizen(user):
    return user.user_type == 'citizen'

def is_staff_member(user):
    return user.user_type in ['data_entry_staff', 'investigator', 'supervisor', 'admin']

def is_investigator(user):
    return user.user_type == 'investigator'

def is_supervisor(user):
    return user.user_type == 'supervisor'

def is_admin(user):
    return user.user_type == 'admin'

def citizen_login(request):
    if request.method == 'POST':
        national_id = request.POST.get('national_id')
        phone_number = request.POST.get('phone_number')
        try:
            user = User.objects.get(national_id=national_id, phone_number=phone_number)
            if user.is_verified:
                # In a real app, send a verification code here
                user.verification_code = '123456'  # Mock code for testing
                user.save()
                request.session['login_user_id'] = user.id
                return redirect('verify_code')
            else:
                messages.error(request, 'Compte non vérifié')
        except User.DoesNotExist:
            messages.error(request, 'Identifiant national ou numéro de téléphone incorrect')
        return render(request, 'auth/citizen_login.html')
    
    return render(request, 'auth/citizen_login.html')

def verify_code(request):
    if request.method == 'POST':
        code = request.POST.get('verification_code')
        user_id = request.session.get('login_user_id')
        
        if user_id:
            try:
                user = User.objects.get(id=user_id, verification_code=code)
                login(request, user)
                user.verification_code = ''
                user.save()
                
                AuditLog.objects.create(
                    user=user,
                    action_type='user_login',
                    description=f'Connexion via vérification SMS pour {user.username}',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    related_citizen=user if user.user_type == 'citizen' else None
                )
                
                # Redirect based on user_type
                if user.user_type == 'citizen':
                    return redirect('citizen_dashboard')
                elif user.user_type == 'admin':
                    return redirect('admin_panel')
                else:  # data_entry_staff, investigator, supervisor
                    return redirect('staff_dashboard')
                
            except User.DoesNotExist:
                messages.error(request, 'Code de vérification invalide')
    
    return render(request, 'auth/verify_code.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'Déconnexion réussie')
    return redirect('citizen_login')

# Citizen Views
@login_required
@user_passes_test(is_citizen)
def citizen_dashboard(request):
    citizen = request.user
    profile, created = CitizenProfile.objects.get_or_create(user=citizen)
    
    # Calculate current social indicator
    current_score = calculate_social_indicator(citizen)
    profile.current_social_indicator = current_score
    profile.last_calculated = timezone.now()
    profile.save()
    
    # Get thresholds
    amo_threshold = get_current_threshold('amo')
    social_aid_threshold = get_current_threshold('social_aid')
    
    # Check eligibility
    amo_eligible = current_score <= amo_threshold and not profile.has_other_insurance
    social_aid_eligible = current_score <= social_aid_threshold
    
    context = {
        'profile': profile,
        'current_score': current_score,
        'amo_threshold': amo_threshold,
        'social_aid_threshold': social_aid_threshold,
        'amo_eligible': amo_eligible,
        'social_aid_eligible': social_aid_eligible,
        'recent_possessions': CitizenPossession.objects.filter(citizen=citizen).order_by('-created_at')[:5],
        'pending_reclamations': Reclamation.objects.filter(citizen=citizen, status='pending').count(),
        'active_applications': Application.objects.filter(citizen=citizen, status__in=['submitted', 'under_review']).count(),
    }
    
    return render(request, 'citizen/dashboard.html', context)

@login_required
@user_passes_test(is_citizen)
def eligibility_calculator(request):
    citizen = request.user
    possessions = CitizenPossession.objects.filter(
        citizen=citizen, 
        status='active'
    ).select_related('possession_type', 'possession_type__category')
    
    calculation_items = []
    total_score = Decimal('0')
    
    for possession in possessions:
        calculation_items.append({
            'possession': possession,
            'points': possession.possession_type.point_value,
            'category': possession.possession_type.category.name
        })
        total_score += possession.possession_type.point_value
    
    # Get thresholds
    amo_threshold = get_current_threshold('amo')
    social_aid_threshold = get_current_threshold('social_aid')
    
    context = {
        'calculation_items': calculation_items,
        'total_score': total_score,
        'amo_threshold': amo_threshold,
        'social_aid_threshold': social_aid_threshold,
        'amo_eligible': total_score <= amo_threshold,
        'social_aid_eligible': total_score <= social_aid_threshold,
    }
    
    return render(request, 'citizen/calculator.html', context)

@login_required
@user_passes_test(is_citizen)
def create_reclamation(request, possession_id):
    possession = get_object_or_404(CitizenPossession, id=possession_id, citizen=request.user)
    
    if request.method == 'POST':
        reason = request.POST.get('reason')
        evidence = request.POST.get('evidence_description')
        
        reclamation = Reclamation.objects.create(
            citizen=request.user,
            possession=possession,
            reason=reason,
            evidence_description=evidence
        )
        
        # Update possession status
        possession.status = 'under_investigation'
        possession.save()
        
        # Log the action
        AuditLog.objects.create(
            user=request.user,
            action_type='reclamation_created',
            description=f'Création d\'une réclamation pour {possession.possession_type.name}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            metadata={'reclamation_id': str(reclamation.id)}
        )
        
        messages.success(request, 'Réclamation soumise avec succès')
        return redirect('citizen_dashboard')
    
    return render(request, 'citizen/create_reclamation.html', {'possession': possession})

@login_required
@user_passes_test(is_citizen)
def my_reclamations(request):
    reclamations = Reclamation.objects.filter(citizen=request.user).order_by('-created_at')
    return render(request, 'citizen/my_reclamations.html', {'reclamations': reclamations})

@login_required
@user_passes_test(is_citizen)
def my_applications(request):
    applications = Application.objects.filter(citizen=request.user).order_by('-created_at')
    return render(request, 'citizen/my_applications.html', {'applications': applications})

@login_required
@user_passes_test(lambda u: u.user_type == 'citizen')
def create_application(request, program_type):
    citizen = request.user
    profile = get_object_or_404(CitizenProfile, user=citizen)
    
    if program_type not in ['amo', 'social_aid']:
        messages.error(request, 'Type de programme invalide.')
        return redirect('citizen_dashboard')
    
    # Check for existing applications (draft, submitted, or under_review)
    existing_application = Application.objects.filter(
        citizen=citizen,
        program_type=program_type,
        status__in=['draft', 'submitted', 'under_review']
    ).first()
    
    if existing_application:
        status_display = {
            'draft': 'brouillon',
            'submitted': 'soumise',
            'under_review': 'en cours d\'examen'
        }
        if existing_application.status == 'draft':
            messages.info(request, f'Vous avez une demande {program_type.upper()} en brouillon. Finalisez-la pour soumettre.')
        else:
            messages.error(request, f'Vous avez déjà une demande {program_type.upper()} ({status_display[existing_application.status]}). Veuillez attendre son traitement.')
        return redirect('my_applications')
    
    # Check if last application was rejected and if a new calculation occurred
    last_application = Application.objects.filter(
        citizen=citizen,
        program_type=program_type
    ).order_by('-submitted_at').first()
    
    if last_application and last_application.status == 'rejected':
        latest_calculation = SocialIndicatorCalculation.objects.filter(
            citizen=citizen,
            calculation_date__gt=last_application.submitted_at
        ).exists()
        is_fresh = profile.last_calculated and profile.last_calculated > last_application.submitted_at
        
        if not (latest_calculation or is_fresh):
            messages.error(request, f'Votre dernière demande {program_type.upper()} a été rejetée. Veuillez recalculer votre indicateur social avant de soumettre une nouvelle demande.')
            return redirect('eligibility_calculator')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            # Get the latest active threshold
            threshold = SocialIndicatorThreshold.objects.filter(
                program_type=program_type,
                is_active=True
            ).order_by('-effective_date').first()
            
            if not threshold:
                messages.error(request, f'Aucun seuil actif défini pour le programme {program_type.upper()}.')
                return redirect('citizen_dashboard')
            
            # Check if social indicator exists
            if profile.current_social_indicator is None:
                messages.error(request, 'Vous devez avoir un indicateur social calculé pour soumettre une demande.')
                return redirect('eligibility_calculator')
            
            if action == 'save_draft':
                application = Application(
                    citizen=citizen,
                    program_type=program_type,
                    status='draft',
                    social_indicator_at_submission=profile.current_social_indicator,
                    threshold_at_submission=threshold.max_score
                )
                application.save()
                messages.success(request, f'Brouillon de demande {program_type.upper()} enregistré.')
                return redirect('my_applications')
            
            application = Application(
                citizen=citizen,
                program_type=program_type,
                status='submitted',
                social_indicator_at_submission=profile.current_social_indicator,
                threshold_at_submission=threshold.max_score,
                submitted_at=timezone.now()
            )
            application.save()
            
            AuditLog.objects.create(
                user=citizen,
                action_type='application_submitted',
                description=f'Demande {program_type.upper()} soumise par {citizen.username}',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                related_citizen=citizen,
                metadata={'application_id': str(application.id)}
            )
            
            messages.success(request, f'Demande {program_type.upper()} soumise avec succès.')
            return redirect('my_applications')
        
        except SocialIndicatorThreshold.DoesNotExist:
            messages.error(request, f'Aucun seuil actif défini pour le programme {program_type.upper()}.')
            return redirect('citizen_dashboard')
    
    try:
        threshold = SocialIndicatorThreshold.objects.filter(
            program_type=program_type,
            is_active=True
        ).order_by('-effective_date').first()
        threshold_value = threshold.max_score if threshold else None
    except SocialIndicatorThreshold.DoesNotExist:
        threshold_value = None
    
    return render(request, 'citizen/create_application.html', {
        'program_type': program_type,
        'social_indicator': profile.current_social_indicator,
        'threshold': threshold_value
    })

@login_required
@user_passes_test(is_staff_member)
def staff_dashboard(request):
    user = request.user
    if user.user_type == 'data_entry_staff':
        return render(request, 'staff/data_entry_dashboard.html', {
            'recent_additions': CitizenPossession.objects.filter(added_by=user).order_by('-created_at')[:10],
            'citizens_count': User.objects.filter(user_type='citizen').count(),
        })
    elif user.user_type == 'investigator':
        pending_investigations = Reclamation.objects.filter(
            assigned_investigator=user,
            status='under_investigation'
        ).order_by('created_at')
        pending_reclamations = Reclamation.objects.filter(
            status='pending',
            assigned_investigator__isnull=True
        ).order_by('created_at')
        return render(request, 'staff/investigator_dashboard.html', {
            'pending_investigations': pending_investigations,
            'pending_reclamations': pending_reclamations,
            'completed_today': Reclamation.objects.filter(
                assigned_investigator=user,
                resolution_date__date=timezone.now().date()
            ).count(),
        })
    elif user.user_type == 'supervisor':
        pending_applications = Application.objects.filter(
            status='submitted'
        ).order_by('submitted_at')
        return render(request, 'staff/supervisor_dashboard.html', {
            'pending_applications': pending_applications,
            'approved_today': Application.objects.filter(
                reviewed_by=user,
                status='approved',
                reviewed_at__date=timezone.now().date()
            ).count(),
        })
    elif user.user_type == 'admin':
        return render(request, 'staff/admin_dashboard.html', {
            'total_users': User.objects.count(),
            'total_applications': Application.objects.count(),
            'pending_reclamations': Reclamation.objects.filter(status='pending').count(),
            'recent_activities': AuditLog.objects.order_by('-timestamp')[:20],
        })

@login_required
@user_passes_test(is_investigator)
def assign_reclamation(request, reclamation_id):
    reclamation = get_object_or_404(Reclamation, id=reclamation_id, status='pending', assigned_investigator__isnull=True)
    if request.method == 'POST':
        reclamation.assigned_investigator = request.user
        reclamation.status = 'under_investigation'
        reclamation.save()
        AuditLog.objects.create(
            user=request.user,
            action_type='reclamation_assigned',
            description=f'Réclamation {reclamation_id} assignée à {request.user.username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            related_citizen=reclamation.citizen,
            metadata={'reclamation_id': str(reclamation_id)}
        )
        messages.success(request, 'Réclamation assignée avec succès')
        return redirect('staff_dashboard')
    return redirect('staff_dashboard')

@login_required
@user_passes_test(is_staff_member)
def manage_citizens(request):
    citizens = User.objects.filter(user_type='citizen').order_by('last_name')
    return render(request, 'staff/manage_citizens.html', {'citizens': citizens})

@login_required
@user_passes_test(is_staff_member)
def citizen_detail(request, citizen_id):
    citizen = get_object_or_404(User, id=citizen_id, user_type='citizen')
    profile = get_object_or_404(CitizenProfile, user=citizen)
    possessions = CitizenPossession.objects.filter(citizen=citizen).order_by('-created_at')
    reclamations = Reclamation.objects.filter(citizen=citizen).order_by('-created_at')
    applications = Application.objects.filter(citizen=citizen).order_by('-created_at')
    
    context = {
        'citizen': citizen,
        'profile': profile,
        'possessions': possessions,
        'reclamations': reclamations,
        'applications': applications,
    }
    return render(request, 'staff/citizen_detail.html', context)

@login_required
@user_passes_test(lambda u: u.user_type == 'data_entry_staff' or u.user_type == 'admin')
def add_possession(request, citizen_id):
    citizen = get_object_or_404(User, id=citizen_id, user_type='citizen')
    
    if request.method == 'POST':
        possession_type_id = request.POST.get('possession_type')
        description = request.POST.get('description')
        acquisition_date = request.POST.get('acquisition_date')
        estimated_value = request.POST.get('estimated_value')
        
        possession_type = get_object_or_404(PossessionType, id=possession_type_id)
        
        possession = CitizenPossession.objects.create(
            citizen=citizen,
            possession_type=possession_type,
            description=description,
            acquisition_date=acquisition_date,
            estimated_value=estimated_value,
            added_by=request.user
        )
        
        AuditLog.objects.create(
            user=request.user,
            action_type='possession_added',
            description=f'Ajout de {possession_type.name} à {citizen.username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            related_citizen=citizen,
            metadata={'possession_id': possession.id}
        )
        
        messages.success(request, 'Possession ajoutée avec succès')
        return redirect('citizen_detail', citizen_id=citizen_id)
    
    categories = PossessionCategory.objects.filter(is_active=True)
    return render(request, 'staff/add_possession.html', {'citizen': citizen, 'categories': categories})


@login_required
@user_passes_test(is_investigator)
def investigate_reclamation(request, reclamation_id):
    reclamation = get_object_or_404(Reclamation, id=reclamation_id, assigned_investigator=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')  # 'approve' or 'reject'
        notes = request.POST.get('notes')
        
        reclamation.investigation_notes = notes
        reclamation.resolution_date = timezone.now()
        
        if action == 'approve':
            reclamation.status = 'approved'
            reclamation.possession.status = 'removed'
            reclamation.possession.save()
        elif action == 'reject':
            reclamation.status = 'rejected'
            fine_amount = request.POST.get('fine_amount', '0')
            Fine.objects.create(
                reclamation=reclamation,
                amount=Decimal(fine_amount),
                reason='Réclamation frauduleuse',
                applied_by=request.user
            )
        
        reclamation.save()
        
        AuditLog.objects.create(
            user=request.user,
            action_type='reclamation_investigated',
            description=f'Investigation de la réclamation {reclamation_id} - {action}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            related_citizen=reclamation.citizen,
            metadata={'reclamation_id': str(reclamation_id)}
        )
        
        messages.success(request, 'Investigation terminée')
        return redirect('staff_dashboard')
    
    return render(request, 'staff/investigate_reclamation.html', {'reclamation': reclamation})

@login_required
@user_passes_test(is_supervisor)
def review_applications(request):
    applications = Application.objects.filter(status='submitted').order_by('submitted_at')
    return render(request, 'staff/review_applications.html', {'applications': applications})

@login_required
@user_passes_test(is_supervisor)
def review_application(request, application_id):
    application = get_object_or_404(Application, id=application_id, status='submitted')
    
    if request.method == 'POST':
        action = request.POST.get('action')  # 'approve' or 'reject'
        notes = request.POST.get('notes')
        
        application.status = action + 'ed'  # 'approved' or 'rejected'
        application.reviewed_by = request.user
        application.review_notes = notes
        application.reviewed_at = timezone.now()
        application.save()
        
        AuditLog.objects.create(
            user=request.user,
            action_type='application_reviewed',
            description=f'Examen de la demande {application_id} - {action}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            related_citizen=application.citizen,
            metadata={'application_id': str(application_id)}
        )
        
        messages.success(request, 'Demande examinée')
        return redirect('review_applications')
    
    return render(request, 'staff/review_application.html', {'application': application})

# Admin Views
@login_required
@user_passes_test(is_admin)
def admin_panel(request):
    return render(request, 'admin/panel.html')

@login_required
@user_passes_test(is_admin)
def manage_possession_types(request):
    categories = PossessionCategory.objects.all()
    types = PossessionType.objects.all()
    
    if request.method == 'POST':
        if 'create_category' in request.POST:
            name = request.POST.get('name')
            description = request.POST.get('description')
            PossessionCategory.objects.create(name=name, description=description)
            messages.success(request, 'Catégorie créée')
        elif 'create_type' in request.POST:
            category_id = request.POST.get('category')
            name = request.POST.get('name')
            description = request.POST.get('description')
            point_value = request.POST.get('point_value')
            category = get_object_or_404(PossessionCategory, id=category_id)
            PossessionType.objects.create(
                category=category,
                name=name,
                description=description,
                point_value=Decimal(point_value)
            )
            messages.success(request, 'Type créé')
        return redirect('manage_possession_types')
    
    return render(request, 'admin/manage_possession_types.html', {'categories': categories, 'types': types})

@login_required
@user_passes_test(is_admin)
def audit_logs(request):
    logs = AuditLog.objects.order_by('-timestamp')
    return render(request, 'admin/audit_logs.html', {'logs': logs})

# AJAX API Views
@login_required
@user_passes_test(is_staff_member)
def get_possession_types_by_category(request, category_id):
    types = PossessionType.objects.filter(category_id=category_id, is_active=True).values('id', 'name', 'point_value')
    return JsonResponse(list(types), safe=False)

@login_required
def get_possession_types(request, category_id):
    types = PossessionType.objects.filter(category_id=category_id).values('id', 'name', 'point_value')
    return JsonResponse(list(types), safe=False)

@login_required
@user_passes_test(is_citizen)
def calculate_score_ajax(request):
    if request.method == 'POST':
        score = calculate_social_indicator(request.user)
        return JsonResponse({'score': float(score)})
    return JsonResponse({'error': 'Requête invalide'}, status=400)

# Utility Functions
def calculate_social_indicator(citizen):
    """Calculate the current social indicator for a citizen"""
    possessions = CitizenPossession.objects.filter(
        citizen=citizen,
        status='active'
    ).select_related('possession_type')
    
    total_score = possessions.aggregate(
        total=Sum('possession_type__point_value')
    )['total'] or Decimal('0')
    
    return total_score

def get_current_threshold(program_type):
    """Get the current threshold for AMO or Social Aid"""
    try:
        threshold = SocialIndicatorThreshold.objects.filter(
            program_type=program_type,
            is_active=True,
            effective_date__lte=timezone.now().date()
        ).order_by('-effective_date').first()
        
        return threshold.max_score if threshold else Decimal('999999')
    except:
        return Decimal('999999')

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# Add to views.py
@login_required
@user_passes_test(lambda u: u.user_type == 'data_entry_staff' or u.user_type == 'admin')
def edit_possession(request, possession_id):
    possession = get_object_or_404(CitizenPossession, id=possession_id)
    if request.method == 'POST':
        possession_type_id = request.POST.get('possession_type')
        description = request.POST.get('description')
        acquisition_date = request.POST.get('acquisition_date')
        estimated_value = request.POST.get('estimated_value')
        
        possession_type = get_object_or_404(PossessionType, id=possession_type_id)
        possession.possession_type = possession_type
        possession.description = description
        possession.acquisition_date = acquisition_date
        possession.estimated_value = Decimal(estimated_value) if estimated_value else None
        possession.save()
        
        AuditLog.objects.create(
            user=request.user,
            action_type='possession_edited',
            description=f'Modification de la possession {possession_type.name} pour {possession.citizen.username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            related_citizen=possession.citizen,
            metadata={'possession_id': possession.id}
        )
        
        messages.success(request, 'Possession modifiée avec succès')
        return redirect('citizen_detail', citizen_id=possession.citizen.id)
    
    categories = PossessionCategory.objects.filter(is_active=True)
    return render(request, 'staff/edit_possession.html', {
        'possession': possession,
        'categories': categories,
    })

@login_required
@user_passes_test(lambda u: u.user_type == 'data_entry_staff' or u.user_type == 'admin')
def delete_possession(request, possession_id):
    possession = get_object_or_404(CitizenPossession, id=possession_id, added_by=request.user)
    if request.method == 'POST':
        citizen_id = possession.citizen.id
        possession_type_name = possession.possession_type.name
        possession.delete()
        
        AuditLog.objects.create(
            user=request.user,
            action_type='possession_deleted',
            description=f'Suppression de la possession {possession_type_name} pour {possession.citizen.username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            related_citizen=possession.citizen,
            metadata={'possession_id': possession_id}
        )
        
        messages.success(request, 'Possession supprimée avec succès')
        return redirect('citizen_detail', citizen_id=citizen_id)
    
    return redirect('citizen_detail', citizen_id=possession.citizen.id)
