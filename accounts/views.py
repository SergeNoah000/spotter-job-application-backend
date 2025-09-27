from django.shortcuts import render
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.contrib.auth import login
from django.db import transaction
from .models import User, Company, UserProfile
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    CompanySerializer, UserProfileSerializer, LoginSerializer,
    ChangePasswordSerializer
)

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
            
            # Mettre à jour last_login
            login(request, user)
            
            return Response({
                'access': str(access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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

class RefreshTokenView(TokenRefreshView):
    """Vue pour rafraîchir le token JWT"""
    pass

class UserProfileView(generics.RetrieveUpdateAPIView):
    """Vue pour consulter et modifier le profil utilisateur"""
    
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user

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

class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Vue pour consulter, modifier et supprimer une entreprise"""
    
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

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
        
        # Sauvegarder avec la compagnie assignée
        user = serializer.save(company=company)
        
        # Créer le profil utilisateur
        from .models import UserProfile
        UserProfile.objects.get_or_create(user=user)

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

# Permission personnalisée
class IsAdminUser(permissions.BasePermission):
    """Permission pour les administrateurs seulement"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_admin()

class IsFleetManagerOrAdmin(permissions.BasePermission):
    """Permission pour les gestionnaires de flotte et administrateurs"""
    
    def has_permission(self, request, view):
        return (request.user and request.user.is_authenticated and 
                request.user.can_manage_users)

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
