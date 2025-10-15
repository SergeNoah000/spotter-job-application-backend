from django.shortcuts import render
from rest_framework import generics, status, permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.contrib.auth import login
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import secrets
import hashlib
from .models import User, Company, UserProfile
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    CompanySerializer, UserProfileSerializer, LoginSerializer,
    ChangePasswordSerializer
)

# Permission personnalisées (définies au début)
class IsAdminUser(permissions.BasePermission):
    """Permission pour les administrateurs seulement"""
    
    def has_permission(self, request, view):
        # Vérification plus robuste
        return (
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'is_admin') and
            request.user.is_admin()
        )

class IsFleetManagerOrAdmin(permissions.BasePermission):
    """Permission pour les gestionnaires de flotte et administrateurs"""
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Vérification de l'existence de l'attribut avant utilisation
        return getattr(request.user, 'can_manage_users', False)


# Vues d'authentification

class LoginView(APIView):
    """Vue pour l'authentification des utilisateurs"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Créer les tokens JWT
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            
            # Mettre à jour last_login et IP
            user.last_login_ip = self.get_client_ip(request)
            user.save(update_fields=['last_login', 'last_login_ip'])
            login(request, user)
            
            # Vérifier si l'utilisateur doit changer son mot de passe
            response_data = {
                'access': str(access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            }
            
            if user.must_change_password:
                response_data['first_login'] = True
                response_data['message'] = 'Vous devez changer votre mot de passe lors de votre première connexion.'
            
            return Response(response_data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_client_ip(self, request):
        """Obtenir l'adresse IP du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class LogoutView(APIView):
    """Vue pour la déconnexion"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response({'message': 'Successfully logged out'})
        except Exception as e:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetRequestView(APIView):
    """Vue pour demander une réinitialisation de mot de passe"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            
            # Générer un token de réinitialisation
            reset_token = secrets.token_urlsafe(32)
            user.password_reset_token = reset_token
            user.password_reset_token_expires = timezone.now() + timedelta(hours=24)
            user.save(update_fields=['password_reset_token', 'password_reset_token_expires'])
            
            # Envoyer l'email (en développement, cela s'affichera dans la console)
            reset_url = f"{request.build_absolute_uri('/')[:-1]}/auth/reset-password/?token={reset_token}&uid={user.id}"
            
            send_mail(
                subject='Réinitialisation de votre mot de passe - Spotter Transport',
                message=f'''
                Bonjour {user.get_full_name()},
                
                Vous avez demandé une réinitialisation de votre mot de passe.
                
                Cliquez sur le lien suivant pour réinitialiser votre mot de passe :
                {reset_url}
                
                Ce lien expirera dans 24 heures.
                
                Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.
                
                Cordialement,
                L'équipe Spotter Transport
                ''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            
            return Response({'message': 'Password reset email sent successfully'})
            
        except User.DoesNotExist:
            # Pour des raisons de sécurité, on retourne le même message
            return Response({'message': 'Password reset email sent successfully'})

class PasswordResetConfirmView(APIView):
    """Vue pour confirmer la réinitialisation de mot de passe"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('newPassword')
        
        if not token or not new_password:
            return Response({'error': 'Token and new password are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_password) < 8:
            return Response({'error': 'Password must be at least 8 characters long'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(
                password_reset_token=token,
                password_reset_token_expires__gt=timezone.now(),
                is_active=True
            )
            
            # Changer le mot de passe
            user.set_password(new_password)
            user.password_reset_token = None
            user.password_reset_token_expires = None
            user.must_change_password = False
            user.save()
            
            return Response({'message': 'Password reset successfully'})
            
        except User.DoesNotExist:
            return Response({'error': 'Invalid or expired reset token'}, status=status.HTTP_400_BAD_REQUEST)

class FirstLoginPasswordChangeView(APIView):
    """Vue pour changer le mot de passe lors de la première connexion"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        user_id = request.data.get('user_id')
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not all([user_id, old_password, new_password]):
            return Response({'error': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_password) < 8:
            return Response({'error': 'Password must be at least 8 characters long'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(id=user_id, is_active=True)
            
            if not user.check_password(old_password):
                return Response({'error': 'Invalid current password'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not user.must_change_password:
                return Response({'error': 'Password change not required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Changer le mot de passe
            user.set_password(new_password)
            user.must_change_password = False
            user.save()
            
            # Créer les tokens JWT après changement de mot de passe
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            
            return Response({
                'access': str(access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data,
                'message': 'Password changed successfully'
            })
            
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_400_BAD_REQUEST)

class RefreshTokenView(TokenRefreshView):
    """Vue pour rafraîchir le token JWT"""
    pass

class UserProfileView(generics.RetrieveUpdateAPIView):
    """Vue pour consulter et modifier le profil utilisateur"""
    
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

class ChangePasswordView(APIView):
    """Vue pour changer le mot de passe"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.updated_by = request.user
            user.save()
            
            return Response({'message': 'Password changed successfully'})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Vues pour les administrateurs

class CompanyListCreateView(generics.ListCreateAPIView):
    """Vue pour lister et créer les entreprises (admin seulement)"""
    
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsAdminUser()]
        return [permissions.IsAuthenticated()]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Vue pour consulter, modifier et supprimer une entreprise"""
    
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

class UserListCreateView(generics.ListCreateAPIView):
    """Vue pour lister et créer les utilisateurs"""
    
    queryset = User.objects.select_related('company', 'profile')
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserCreateSerializer
        return UserSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = User.objects.select_related('company', 'profile')
        
        if user.is_admin():
            # Admin peut voir tous les utilisateurs
            return queryset
        elif user.is_fleet_manager():
            # Fleet manager peut voir les utilisateurs de sa compagnie
            return queryset.filter(company=user.company)
        else:
            # Driver ne peut voir que son propre profil
            return queryset.filter(id=user.id)
    
    def perform_create(self, serializer):
        # Seuls les admins et fleet managers peuvent créer des utilisateurs
        if not self.request.user.can_manage_users:
            raise permissions.PermissionDenied("Not authorized to create users")
        
        # Assigner automatiquement la compagnie de l'utilisateur connecté
        company = self.request.user.company
        if not company:
            raise serializers.ValidationError("User must belong to a company to create drivers")
        
        # Générer un mot de passe temporaire
        temp_password = secrets.token_urlsafe(12)
        
        # Sauvegarder avec la compagnie assignée et must_change_password=True
        user = serializer.save(
            company=company, 
            created_by=self.request.user,
            must_change_password=True
        )
        user.set_password(temp_password)
        user.save()
        
        # Créer le profil utilisateur
        UserProfile.objects.get_or_create(
            user=user,
            defaults={'created_by': self.request.user}
        )
        
        # Envoyer email d'activation avec mot de passe temporaire
        self.send_activation_email(user, temp_password)
    
    def send_activation_email(self, user, temp_password):
        """Envoie un email d'activation avec mot de passe temporaire"""
        try:
            send_mail(
                subject='Bienvenue sur Spotter Transport - Activation de votre compte',
                message=f'''
                Bonjour {user.get_full_name()},
                
                Votre compte Spotter Transport a été créé par {self.request.user.get_full_name()}.
                
                Informations de connexion :
                Email : {user.email}
                Mot de passe temporaire : {temp_password}
                
                Pour des raisons de sécurité, vous devrez changer votre mot de passe lors de votre première connexion.
                
                Connectez-vous sur : {self.request.build_absolute_uri('/')[:-1]}/login
                
                Cordialement,
                L'équipe Spotter Transport
                ''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            # Log l'erreur mais ne pas faire échouer la création de l'utilisateur
            pass

class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Vue pour consulter, modifier et supprimer un utilisateur"""
    
    queryset = User.objects.select_related('company', 'profile')
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_object(self):
        user = self.request.user
        obj = super().get_object()
        
        # Vérifier les permissions
        if user.is_admin():
            return obj
        elif user.is_fleet_manager() and obj.company == user.company:
            return obj
        elif obj == user:
            return obj
        else:
            raise permissions.PermissionDenied("Not authorized to access this user")

class UserProfileUpdateView(generics.RetrieveUpdateAPIView):
    """Vue pour modifier le profil étendu d'un utilisateur"""
    
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        user_id = self.kwargs.get('user_id')
        if user_id:
            user = User.objects.get(id=user_id)
            # Vérifier les permissions comme dans UserDetailView
            if (self.request.user.is_admin() or 
                (self.request.user.is_fleet_manager() and user.company == self.request.user.company) or
                user == self.request.user):
                profile, created = UserProfile.objects.get_or_create(user=user)
                return profile
            else:
                raise permissions.PermissionDenied("Not authorized")
        else:
            # Profil de l'utilisateur connecté
            profile, created = UserProfile.objects.get_or_create(user=self.request.user)
            return profile

# Vues pour les statistiques (admin/fleet manager)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """Statistiques pour le dashboard"""
    
    user = request.user
    
    if user.is_admin():
        # Stats globales pour admin
        stats = {
            'total_companies': Company.objects.filter(is_active=True).count(),
            'total_users': User.objects.filter(is_active=True).count(),
            'total_drivers': User.objects.filter(user_type='DRIVER', is_active=True).count(),
            'total_fleet_managers': User.objects.filter(user_type='FLEET_MANAGER', is_active=True).count(),
        }
    elif user.is_fleet_manager():
        # Stats pour sa compagnie
        stats = {
            'company_drivers': User.objects.filter(
                company=user.company, 
                user_type='DRIVER', 
                is_active=True
            ).count(),
            'company_vehicles': user.company.vehicles.filter(is_active=True).count(),
            'active_trips': user.company.users.filter(
                trips__status='IN_PROGRESS'
            ).count(),
        }
    else:
        # Stats pour conducteur
        stats = {
            'total_trips': user.trips.count(),
            'completed_trips': user.trips.filter(status='COMPLETED').count(),
            'total_miles': user.profile.total_miles if hasattr(user, 'profile') else 0,
        }
    
    return Response(stats)
