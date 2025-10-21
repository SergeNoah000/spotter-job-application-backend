from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from datetime import datetime, timedelta
from accounts.models import User, Company
from trips.models import Trip, Vehicle
from eld_logs.models import ELDLog, DutyStatusEntry
from eld_logs.views import detect_implicit_trip


class ImplicitTripDetectionTestCase(TestCase):
    """
    Tests pour la détection automatique du voyage implicite
    """
    
    def setUp(self):
        """Configuration initiale des tests"""
        # Créer une compagnie
        self.company = Company.objects.create(
            name='Test Transport Co',
            dot_number='1234567',
            phone='555-0100'
        )
        
        # Créer un véhicule
        self.vehicle = Vehicle.objects.create(
            company=self.company,
            vehicle_number='TRUCK-001',
            vin='1HGCM82633A123456',
            make='Freightliner',
            model='Cascadia',
            year=2022
        )
        
        # Créer un conducteur
        self.driver = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='John',
            last_name='Driver',
            user_type='DRIVER',
            company=self.company
        )
        self.driver.assigned_vehicle = self.vehicle
        self.driver.save()
        
        # Créer un dispatcher
        self.dispatcher = User.objects.create_user(
            email='dispatcher@test.com',
            password='testpass123',
            first_name='Jane',
            last_name='Dispatcher',
            user_type='FLEET_MANAGER',
            company=self.company
        )
        
        # Client API
        self.client = APIClient()
    
    def test_detect_implicit_trip_with_in_progress_trip(self):
        """Test : Détection d'un voyage en cours"""
        # Créer un voyage en cours
        trip = Trip.objects.create(
            company=self.company,
            trip_number='TRIP-001',
            driver=self.driver,
            vehicle=self.vehicle,
            origin='Montreal',
            destination='Toronto',
            pickup_location='123 Pickup St',
            delivery_location='456 Delivery Ave',
            status='in_progress',
            actual_departure=datetime.now() - timedelta(hours=2)
        )
        
        # Tester la détection
        detected_trip = detect_implicit_trip(self.driver)
        
        self.assertIsNotNone(detected_trip)
        self.assertEqual(detected_trip.id, trip.id)
        self.assertEqual(detected_trip.status, 'in_progress')
    
    def test_detect_implicit_trip_with_assigned_trip(self):
        """Test : Détection d'un voyage assigné (pas encore démarré)"""
        # Créer un voyage assigné
        trip = Trip.objects.create(
            company=self.company,
            trip_number='TRIP-002',
            driver=self.driver,
            vehicle=self.vehicle,
            origin='Quebec City',
            destination='Ottawa',
            pickup_location='789 Start St',
            delivery_location='321 End Ave',
            status='assigned',
            scheduled_departure=datetime.now() + timedelta(hours=1)
        )
        
        # Tester la détection
        detected_trip = detect_implicit_trip(self.driver)
        
        self.assertIsNotNone(detected_trip)
        self.assertEqual(detected_trip.id, trip.id)
        self.assertEqual(detected_trip.status, 'assigned')
    
    def test_detect_implicit_trip_no_active_trip(self):
        """Test : Aucun voyage actif détecté"""
        # Pas de voyage créé
        detected_trip = detect_implicit_trip(self.driver)
        
        self.assertIsNone(detected_trip)
    
    def test_detect_implicit_trip_completed_trip_ignored(self):
        """Test : Les voyages complétés sont ignorés"""
        # Créer un voyage complété
        Trip.objects.create(
            company=self.company,
            trip_number='TRIP-003',
            driver=self.driver,
            vehicle=self.vehicle,
            origin='Montreal',
            destination='Toronto',
            pickup_location='123 Pickup St',
            delivery_location='456 Delivery Ave',
            status='completed',
            actual_departure=datetime.now() - timedelta(hours=10),
            actual_arrival=datetime.now() - timedelta(hours=2)
        )
        
        # Tester la détection
        detected_trip = detect_implicit_trip(self.driver)
        
        self.assertIsNone(detected_trip)


class DutyStatusChangeTestCase(TestCase):
    """
    Tests pour le changement de statut sans sélection manuelle de voyage
    """
    
    def setUp(self):
        """Configuration initiale"""
        self.company = Company.objects.create(
            name='Test Transport Co',
            dot_number='1234567',
            phone='555-0100'
        )
        
        self.vehicle = Vehicle.objects.create(
            company=self.company,
            vehicle_number='TRUCK-001',
            vin='1HGCM82633A123456',
            make='Freightliner',
            model='Cascadia',
            year=2022
        )
        
        self.driver = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='John',
            last_name='Driver',
            user_type='DRIVER',
            company=self.company
        )
        self.driver.assigned_vehicle = self.vehicle
        self.driver.save()
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.driver)
    
    def test_change_status_without_trip(self):
        """Test : Changer de statut sans voyage actif"""
        url = reverse('eld_logs:change_duty_status')
        data = {
            'status': 'ON_DUTY_NOT_DRIVING',
            'location': 'Montreal, QC'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIsNone(response.data.get('implicit_trip'))
    
    def test_change_status_with_implicit_trip(self):
        """Test : Changer de statut avec voyage implicite détecté"""
        # Créer un voyage en cours
        trip = Trip.objects.create(
            company=self.company,
            trip_number='TRIP-001',
            driver=self.driver,
            vehicle=self.vehicle,
            origin='Montreal',
            destination='Toronto',
            pickup_location='123 Pickup St',
            delivery_location='456 Delivery Ave',
            status='in_progress',
            actual_departure=datetime.now() - timedelta(hours=1)
        )
        
        url = reverse('eld_logs:change_duty_status')
        data = {
            'status': 'DRIVING',
            'location': 'Highway 401, ON'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIsNotNone(response.data.get('implicit_trip'))
        self.assertEqual(response.data['implicit_trip']['id'], str(trip.id))
    
    def test_get_driver_activity_with_implicit_trip(self):
        """Test : Récupérer l'activité du conducteur avec voyage implicite"""
        # Créer un voyage en cours
        trip = Trip.objects.create(
            company=self.company,
            trip_number='TRIP-002',
            driver=self.driver,
            vehicle=self.vehicle,
            origin='Quebec City',
            destination='Ottawa',
            pickup_location='789 Start St',
            delivery_location='321 End Ave',
            status='in_progress',
            actual_departure=datetime.now() - timedelta(hours=3)
        )
        
        # Créer quelques segments
        eld_log, _ = ELDLog.objects.get_or_create(
            driver=self.driver,
            log_date=datetime.now().date(),
            defaults={
                'vehicle': self.vehicle,
                'vehicle_number': self.vehicle.vehicle_number,
                'duty_status': 'off_duty',
                'start_time': datetime.now()
            }
        )
        
        DutyStatusEntry.objects.create(
            eld_log=eld_log,
            status='DRIVING',
            start_time=datetime.now() - timedelta(hours=2),
            end_time=datetime.now() - timedelta(hours=1),
            location='Highway 20, QC'
        )
        
        url = reverse('eld_logs:get_driver_activity')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIsNotNone(response.data.get('implicit_trip'))
        self.assertEqual(response.data['implicit_trip']['id'], str(trip.id))
        self.assertIn('hos_statistics', response.data)
        self.assertIn('daily_totals', response.data)


class HOSCalculationTestCase(TestCase):
    """
    Tests pour les calculs HOS (Hours of Service)
    """
    
    def setUp(self):
        """Configuration initiale"""
        self.company = Company.objects.create(
            name='Test Transport Co',
            dot_number='1234567',
            phone='555-0100'
        )
        
        self.vehicle = Vehicle.objects.create(
            company=self.company,
            vehicle_number='TRUCK-001',
            vin='1HGCM82633A123456',
            make='Freightliner',
            model='Cascadia',
            year=2022
        )
        
        self.driver = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='John',
            last_name='Driver',
            user_type='DRIVER',
            company=self.company
        )
        self.driver.assigned_vehicle = self.vehicle
        self.driver.save()
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.driver)
    
    def test_hos_calculation_with_multiple_segments(self):
        """Test : Calcul HOS avec plusieurs segments"""
        # Créer un log ELD
        eld_log = ELDLog.objects.create(
            driver=self.driver,
            log_date=datetime.now().date(),
            vehicle=self.vehicle,
            vehicle_number=self.vehicle.vehicle_number,
            duty_status='off_duty',
            start_time=datetime.now() - timedelta(hours=8)
        )
        
        # Créer plusieurs segments
        base_time = datetime.now() - timedelta(hours=8)
        
        # 2 heures de conduite
        DutyStatusEntry.objects.create(
            eld_log=eld_log,
            status='DRIVING',
            start_time=base_time,
            end_time=base_time + timedelta(hours=2),
            location='Highway 401'
        )
        
        # 1 heure en service (non conduite)
        DutyStatusEntry.objects.create(
            eld_log=eld_log,
            status='ON_DUTY_NOT_DRIVING',
            start_time=base_time + timedelta(hours=2),
            end_time=base_time + timedelta(hours=3),
            location='Rest Area'
        )
        
        # 3 heures hors service
        DutyStatusEntry.objects.create(
            eld_log=eld_log,
            status='OFF_DUTY',
            start_time=base_time + timedelta(hours=3),
            end_time=base_time + timedelta(hours=6),
            location='Rest Area'
        )
        
        url = reverse('eld_logs:get_driver_activity')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        hos_stats = response.data['hos_statistics']
        
        self.assertEqual(hos_stats['driving_time'], 2.0)
        self.assertEqual(hos_stats['on_duty_time'], 1.0)
        self.assertEqual(hos_stats['off_duty_time'], 3.0)
