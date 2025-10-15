"""
Service de calcul des Hours of Service (HOS) selon les règles FMCSA
"""
import requests
from datetime import datetime, timedelta
from django.conf import settings
from geopy.distance import geodesic
from .models import RestStop
import logging
import math
from typing import List, Dict, Optional, Tuple
import json

logger = logging.getLogger(__name__)

class NominatimService:
    """Service de géocodage utilisant Nominatim OpenStreetMap"""
    
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org"
        self.headers = {
            'User-Agent': 'SpotterApp/1.0 (contact@spotter.com)'
        }
        # OpenRouteService pour le calcul d'itinéraires
        self.ors_api_key = settings.OPENROUTE_API_KEY if hasattr(settings, 'OPENROUTE_API_KEY') else None
        self.ors_base_url = "https://api.openrouteservice.org/v2"
    
    def search_address(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Recherche d'adresses avec autocomplétion
        """
        try:
            params = {
                'q': query,
                'format': 'json',
                'limit': limit,
                'addressdetails': 1,
                # 'countrycodes': 'us,ca',  # Limiter aux US et Canada pour le transport
                'extratags': 1
            }
            
            response = requests.get(
                f"{self.base_url}/search",
                params=params,
                headers=self.headers,
                timeout=5
            )
            
            if response.status_code == 200:
                results = response.json()
                suggestions = []
                
                for result in results:
                    # Formatage adapté pour l'interface
                    suggestion = {
                        'place_id': result.get('place_id'),
                        'display_name': result.get('display_name'),
                        'lat': float(result.get('lat')),
                        'lng': float(result.get('lon')),
                        'type': result.get('type', ''),
                        'importance': result.get('importance', 0),
                        'address': {
                            'house_number': result.get('address', {}).get('house_number', ''),
                            'road': result.get('address', {}).get('road', ''),
                            'city': result.get('address', {}).get('city', ''),
                            'state': result.get('address', {}).get('state', ''),
                            'postcode': result.get('address', {}).get('postcode', ''),
                            'country': result.get('address', {}).get('country', ''),
                        },
                        'bbox': result.get('boundingbox', [])
                    }
                    suggestions.append(suggestion)
                
                return suggestions
            else:
                logger.error(f"Nominatim search error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error in Nominatim search: {str(e)}")
            return []
    
    def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        """
        Géocodage inverse : coordonnées vers adresse
        """
        try:
            params = {
                'lat': lat,
                'lon': lng,
                'format': 'json',
                'addressdetails': 1
            }
            
            response = requests.get(
                f"{self.base_url}/reverse",
                params=params,
                headers=self.headers,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'display_name': result.get('display_name'),
                    'address': result.get('address', {}),
                    'lat': lat,
                    'lng': lng
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error in reverse geocoding: {str(e)}")
            return None
    
    def geocode_address(self, address: str) -> Optional[Dict]:
        """
        Géocoder une adresse simple
        """
        results = self.search_address(address, limit=1)
        return results[0] if results else None
    
    def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculer la distance entre deux points (formule de Haversine)
        Retourne la distance en kilomètres
        """
        R = 6371  # Rayon de la Terre en km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def calculate_route(self, origin: Dict, destination: Dict, waypoints: List[Dict] = None) -> Optional[Dict]:
        """
        Calculer un itinéraire avec OpenRouteService
        """
        try:
            # Extraire les coordonnées
            if isinstance(origin, dict) and 'lng' in origin and 'lat' in origin:
                origin_coords = [origin['lng'], origin['lat']]
            else:
                origin_coords = origin
            
            if isinstance(destination, dict) and 'lng' in destination and 'lat' in destination:
                dest_coords = [destination['lng'], destination['lat']]
            else:
                dest_coords = destination
            
            # Si on a une clé API OpenRouteService, utiliser le service
            if self.ors_api_key:
                try:
                    return self._calculate_route_with_ors(origin_coords, dest_coords, waypoints)
                except Exception as ors_error:
                    logger.warning(f"OpenRouteService error, falling back to simple calculation: {str(ors_error)}")
            
            # Sinon, calculer une route simple
            distance_km = self.calculate_distance(
                origin_coords[1], origin_coords[0],
                dest_coords[1], dest_coords[0]
            )
            
            # Durée estimée (60 km/h en moyenne)
            duration_minutes = int(distance_km * 1.2)  # Facteur de 1.2 pour les routes réelles
            
            # Créer une route simple (ligne droite avec quelques points intermédiaires)
            route_points = self._generate_route_points(origin_coords, dest_coords)
            
            return {
                'distance_km': round(distance_km, 2),
                'duration_minutes': duration_minutes,
                'polyline': self._encode_polyline(route_points),
                'route_points': route_points,
                'instructions': [
                    {
                        'instruction': f"Dirigez-vous vers la destination",
                        'distance_km': distance_km,
                        'duration_minutes': duration_minutes
                    }
                ],
                'bbox': [
                    min(origin_coords[1], dest_coords[1]),  # min lat
                    min(origin_coords[0], dest_coords[0]),  # min lng
                    max(origin_coords[1], dest_coords[1]),  # max lat
                    max(origin_coords[0], dest_coords[0])   # max lng
                ]
            }
            
        except Exception as e:
            logger.error(f"Error calculating route: {str(e)}")
            return None
    
    def _calculate_route_with_ors(self, origin_coords: List[float], dest_coords: List[float], waypoints: List[Dict] = None) -> Optional[Dict]:
        """
        Calculer un itinéraire avec OpenRouteService (vraies routes)
        """
        try:
            # Construire la liste des coordonnées
            coordinates = [origin_coords]
            
            if waypoints:
                for wp in waypoints:
                    if isinstance(wp, dict) and 'lng' in wp and 'lat' in wp:
                        coordinates.append([wp['lng'], wp['lat']])
            
            coordinates.append(dest_coords)
            
            # Appel à l'API OpenRouteService
            url = f"{self.ors_base_url}/directions/driving-car/geojson"  # Utiliser le format geojson
            headers = {
                'Authorization': self.ors_api_key,
                'Content-Type': 'application/json; charset=utf-8',
                'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8'
            }
            
            payload = {
                'coordinates': coordinates,
                'instructions': True,
                'units': 'km',
                'geometry': True  # S'assurer que la géométrie est incluse
            }
            
            logger.info(f"Calling OpenRouteService with {len(coordinates)} coordinates")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"ORS Response keys: {data.keys()}")
                
                # OpenRouteService retourne un GeoJSON
                if 'features' not in data or len(data['features']) == 0:
                    raise ValueError("No features found in ORS GeoJSON response")
                
                feature = data['features'][0]
                properties = feature.get('properties', {})
                geometry = feature.get('geometry', {})
                
                # Extraire les coordonnées de la géométrie GeoJSON
                if geometry.get('type') == 'LineString' and 'coordinates' in geometry:
                    route_coords = geometry['coordinates']
                    logger.info(f"Extracted {len(route_coords)} route points")
                else:
                    logger.warning("No LineString geometry found, using fallback")
                    route_coords = [origin_coords, dest_coords]
                
                # Extraire les segments et instructions
                instructions = []
                segments = properties.get('segments', [])
                
                for segment in segments:
                    for step in segment.get('steps', []):
                        instructions.append({
                            'instruction': step.get('instruction', ''),
                            'distance_km': step.get('distance', 0) / 1000,  # Convertir mètres en km
                            'duration_minutes': step.get('duration', 0) / 60,  # Convertir secondes en minutes
                            'name': step.get('name', ''),
                            'type': step.get('type', 0)
                        })
                
                # Extraire le résumé (summary)
                summary = properties.get('summary', {})
                distance_km = summary.get('distance', 0) / 1000  # Convertir de mètres en km
                duration_minutes = summary.get('duration', 0) / 60  # Convertir de secondes en minutes
                
                # Calculer la bounding box
                lats = [coord[1] for coord in route_coords]
                lngs = [coord[0] for coord in route_coords]
                
                result = {
                    'distance_km': round(distance_km, 2),
                    'duration_minutes': int(duration_minutes),
                    'polyline': self._encode_polyline(route_coords),
                    'route_points': route_coords,
                    'instructions': instructions if instructions else [{
                        'instruction': 'Suivez l\'itinéraire',
                        'distance_km': distance_km,
                        'duration_minutes': duration_minutes
                    }],
                    'bbox': [
                        min(lats),  # min lat
                        min(lngs),  # min lng
                        max(lats),  # max lat
                        max(lngs)   # max lng
                    ]
                }
                
                logger.info(f"Route calculated: {distance_km:.2f} km, {int(duration_minutes)} min, {len(route_coords)} points")
                return result
                
            else:
                error_text = response.text
                logger.error(f"OpenRouteService API error: {response.status_code}")
                logger.error(f"Error details: {error_text}")
                
                # Si l'erreur est due à la clé API, afficher un message clair
                if response.status_code == 401 or response.status_code == 403:
                    logger.error("API Key issue - Please check your OPENROUTE_API_KEY in .env")
                
                raise ValueError(f"ORS API returned status {response.status_code}: {error_text}")
                
        except requests.exceptions.Timeout:
            logger.error("OpenRouteService request timeout")
            raise ValueError("Timeout while contacting OpenRouteService")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error in OpenRouteService: {str(e)}")
            raise ValueError(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in OpenRouteService calculation: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _generate_route_points(self, origin: List[float], destination: List[float], num_points: int = 10) -> List[List[float]]:
        """
        Générer des points intermédiaires pour la route
        """
        points = [origin]
        
        for i in range(1, num_points):
            ratio = i / num_points
            lat = origin[1] + (destination[1] - origin[1]) * ratio
            lng = origin[0] + (destination[0] - origin[0]) * ratio
            points.append([lng, lat])
        
        points.append(destination)
        return points
    
    def _encode_polyline(self, points: List[List[float]]) -> str:
        """
        Encoder les points en polyline (version simple)
        En production, utiliser l'algorithme de Google Polyline
        """
        return json.dumps([[p[1], p[0]] for p in points])  # [lat, lng] format


class HOSCalculator:
    """Calculateur HOS amélioré pour la planification de voyages"""
    
    def __init__(self, trip_data: Dict):
        self.trip_data = trip_data
        self.nominatim = NominatimService()
    
    def calculate_trip_schedule(self) -> Dict:
        """
        Calculer le planning complet du voyage avec HOS
        """
        try:
            # Géocoder les adresses si nécessaire
            origin = self._geocode_location(self.trip_data.get('pickup_location'))
            destination = self._geocode_location(self.trip_data.get('dropoff_location'))
            
            if not origin or not destination:
                raise ValueError("Impossible de géocoder les adresses")
            
            # Calculer la route
            route = self.nominatim.calculate_route(origin, destination)
            if not route:
                raise ValueError("Impossible de calculer l'itinéraire")
            
            # Calculer les pauses obligatoires selon HOS
            breaks = self._calculate_mandatory_breaks(route['duration_minutes'])
            
            # Planifier le voyage
            schedule = {
                'origin': origin,
                'destination': destination,
                'route': route,
                'total_duration_minutes': route['duration_minutes'] + sum(b['duration_minutes'] for b in breaks),
                'driving_duration_minutes': route['duration_minutes'],
                'breaks': breaks,
                'estimated_arrival': self._calculate_arrival_time(route['duration_minutes'], breaks),
                'hos_compliant': True
            }
            
            return schedule
            
        except Exception as e:
            logger.error(f"Error in trip calculation: {str(e)}")
            raise
    
    def _geocode_location(self, location: str) -> Optional[Dict]:
        """
        Géocoder une localisation
        """
        if not location:
            return None
        
        results = self.nominatim.search_address(location, limit=1)
        return results[0] if results else None
    
    def _calculate_mandatory_breaks(self, driving_minutes: int) -> List[Dict]:
        """
        Calculer les pauses obligatoires selon les règles HOS
        """
        breaks = []
        
        # Pause de 30 minutes après 8h de conduite
        if driving_minutes > 480:  # 8 heures
            breaks.append({
                'type': 'mandatory_break',
                'duration_minutes': 30,
                'reason': 'Pause obligatoire après 8h de conduite',
                'at_minutes': 480
            })
        
        # Pause de 10h après 11h de conduite (fin de service)
        if driving_minutes > 660:  # 11 heures
            breaks.append({
                'type': 'end_of_service',
                'duration_minutes': 600,  # 10 heures
                'reason': 'Repos obligatoire après 11h de conduite',
                'at_minutes': 660
            })
        
        return breaks
    
    def _calculate_arrival_time(self, driving_minutes: int, breaks: List[Dict]) -> str:
        """
        Calculer l'heure d'arrivée estimée
        """
        from datetime import datetime, timedelta
        
        start_time = datetime.now()
        total_minutes = driving_minutes + sum(b['duration_minutes'] for b in breaks)
        arrival_time = start_time + timedelta(minutes=total_minutes)
        
        return arrival_time.isoformat()