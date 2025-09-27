import json
import logging
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

class GlobalErrorHandlerMiddleware(MiddlewareMixin):
    """Middleware pour la gestion globale des erreurs"""
    
    def process_exception(self, request, exception):
        """Traite toutes les exceptions non gérées"""
        
        # Log l'erreur
        logger.error(f"Erreur non gérée: {str(exception)}", exc_info=True)
        
        # En mode debug, laisser Django gérer
        if settings.DEBUG:
            return None
        
        # Préparer la réponse d'erreur
        error_response = {
            'error': 'Une erreur interne s\'est produite',
            'message': 'Veuillez réessayer plus tard ou contacter le support',
            'timestamp': str(timezone.now())
        }
        
        # Différents types d'erreurs
        if isinstance(exception, ValidationError):
            error_response['error'] = 'Erreur de validation'
            error_response['message'] = str(exception)
            status_code = 400
        elif isinstance(exception, PermissionError):
            error_response['error'] = 'Accès refusé'
            error_response['message'] = 'Vous n\'avez pas les permissions nécessaires'
            status_code = 403
        else:
            status_code = 500
        
        return JsonResponse(error_response, status=status_code)


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Middleware pour ajouter des en-têtes de sécurité"""
    
    def process_response(self, request, response):
        """Ajoute les en-têtes de sécurité à toutes les réponses"""
        
        # En-têtes de sécurité
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content Security Policy
        if not settings.DEBUG:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "font-src 'self'; "
                "connect-src 'self';"
            )
        
        return response


class RateLimitMiddleware(MiddlewareMixin):
    """Middleware simple de limitation du taux de requêtes"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.request_counts = {}
        super().__init__(get_response)
    
    def process_request(self, request):
        """Vérifie le taux de requêtes par IP"""
        
        # Obtenir l'IP du client
        ip = self.get_client_ip(request)
        
        # Compter les requêtes
        current_time = time.time()
        minute = int(current_time // 60)
        
        if ip not in self.request_counts:
            self.request_counts[ip] = {}
        
        if minute not in self.request_counts[ip]:
            self.request_counts[ip][minute] = 0
        
        self.request_counts[ip][minute] += 1
        
        # Nettoyer les anciennes entrées
        for old_minute in list(self.request_counts[ip].keys()):
            if old_minute < minute - 5:  # Garder seulement 5 minutes
                del self.request_counts[ip][old_minute]
        
        # Vérifier la limite (60 requêtes par minute)
        if self.request_counts[ip][minute] > 60:
            return JsonResponse({
                'error': 'Trop de requêtes',
                'message': 'Limite de taux dépassée. Veuillez réessayer plus tard.'
            }, status=429)
        
        return None
    
    def get_client_ip(self, request):
        """Obtient l'IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware pour logger les requêtes importantes"""
    
    def process_request(self, request):
        """Log les requêtes sensibles"""
        
        sensitive_paths = ['/api/auth/login/', '/api/auth/register/', '/api/trips/']
        
        if any(request.path.startswith(path) for path in sensitive_paths):
            logger.info(f"Requête {request.method} sur {request.path} depuis {self.get_client_ip(request)}")
    
    def get_client_ip(self, request):
        """Obtient l'IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip