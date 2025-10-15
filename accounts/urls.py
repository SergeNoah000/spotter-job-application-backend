from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentification
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('token/refresh/', views.RefreshTokenView.as_view(), name='token_refresh'),
    
    # Réinitialisation de mot de passe
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('first-login/change-password/', views.FirstLoginPasswordChangeView.as_view(), name='first_login_password_change'),
    
    # Profil utilisateur
    path('profile/', views.UserProfileView.as_view(), name='user_profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
    # Gestion des utilisateurs
    path('users/', views.UserListCreateView.as_view(), name='user_list_create'),
    path('users/<uuid:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<uuid:user_id>/profile/', views.UserProfileUpdateView.as_view(), name='user_profile_update'),
    
    # Gestion des entreprises
    path('companies/', views.CompanyListCreateView.as_view(), name='company_list_create'),
    path('companies/<uuid:pk>/', views.CompanyDetailView.as_view(), name='company_detail'),
    
    # Statistiques
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),
]