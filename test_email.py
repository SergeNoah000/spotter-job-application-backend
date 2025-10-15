#!/usr/bin/env python
import os
import django
from django.conf import settings

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spotter_project.settings')
django.setup()

from django.core.mail import send_mail
from django.core.mail import get_connection
import traceback

def test_email_configuration():
    """Test de la configuration email"""
    print("=== Test de configuration email ===")
    
    # Affichage de la configuration
    print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
    print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
    print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
    print(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
    print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
    print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    print("=" * 50)
    
    try:
        # Test de connexion
        print("Test de connexion au serveur SMTP...")
        connection = get_connection()
        connection.open()
        print("✅ Connexion SMTP réussie")
        connection.close()
        
        # Test d'envoi d'email
        print("Test d'envoi d'email...")
        result = send_mail(
            subject='Test Email Spotter Transport',
            message='Ceci est un test pour vérifier la configuration email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['gaetan.noah@facsciences-uy1.cm'],
            fail_silently=False,
        )
        
        if result == 1:
            print("✅ Email envoyé avec succès!")
        else:
            print("❌ Échec de l'envoi de l'email")
            
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        print("Trace complète:")
        traceback.print_exc()

if __name__ == "__main__":
    test_email_configuration()