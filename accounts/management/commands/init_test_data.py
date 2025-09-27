from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import User, Company
import uuid

class Command(BaseCommand):
    help = 'Initialise les données de test pour Spotter'

    def handle(self, *args, **options):
        with transaction.atomic():
            # Créer une compagnie de test si elle n'existe pas
            company, created = Company.objects.get_or_create(
                name='Spotter Transport Demo',
                defaults={
                    'address': '123 Rue du Transport, 75001 Paris',
                    'dot_number': '123456',
                    'phone': '+33123456789',
                    'email': 'contact@spotter-transport.com',
                    'operation_schedule': '8_DAY'
                }
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Compagnie créée: {company.name}')
                )
            else:
                self.stdout.write(f'Compagnie existante: {company.name}')

            # Créer un utilisateur admin si il n'existe pas
            admin_user, created = User.objects.get_or_create(
                email='admin@spotter.com',
                defaults={
                    'first_name': 'Admin',
                    'last_name': 'Spotter',
                    'user_type': 'ADMIN',
                    'phone_number': '+33123456789',
                    'company': company,
                    'is_staff': True,
                    'is_superuser': True,
                    'is_active': True
                }
            )
            
            if created:
                admin_user.set_password('admin123')
                admin_user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Admin créé: {admin_user.email}')
                )
            else:
                self.stdout.write(f'Admin existant: {admin_user.email}')

            # Créer un gestionnaire de flotte de test
            manager_user, created = User.objects.get_or_create(
                email='manager@spotter.com',
                defaults={
                    'first_name': 'Manager',
                    'last_name': 'Fleet',
                    'user_type': 'FLEET_MANAGER',
                    'phone_number': '+33123456790',
                    'company': company,
                    'is_active': True
                }
            )
            
            if created:
                manager_user.set_password('manager123')
                manager_user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Manager créé: {manager_user.email}')
                )
            else:
                self.stdout.write(f'Manager existant: {manager_user.email}')

            # Créer quelques conducteurs de test
            drivers_data = [
                {
                    'email': 'jean.dupont@spotter.com',
                    'first_name': 'Jean',
                    'last_name': 'Dupont',
                    'phone_number': '+33123456791',
                    'cdl_number': 'CDL123456'
                },
                {
                    'email': 'marie.martin@spotter.com',
                    'first_name': 'Marie',
                    'last_name': 'Martin',
                    'phone_number': '+33123456792',
                    'cdl_number': 'CDL654321'
                }
            ]

            for driver_data in drivers_data:
                driver, created = User.objects.get_or_create(
                    email=driver_data['email'],
                    defaults={
                        **driver_data,
                        'user_type': 'DRIVER',
                        'company': company,
                        'is_active': True
                    }
                )
                
                if created:
                    driver.set_password('driver123')
                    driver.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'Conducteur créé: {driver.email}')
                    )
                else:
                    self.stdout.write(f'Conducteur existant: {driver.email}')

            self.stdout.write(
                self.style.SUCCESS('\n=== DONNÉES DE TEST INITIALISÉES ===')
            )
            self.stdout.write(f'Admin: admin@spotter.com / admin123')
            self.stdout.write(f'Manager: manager@spotter.com / manager123')
            self.stdout.write(f'Conducteurs: jean.dupont@spotter.com / driver123')
            self.stdout.write(f'            marie.martin@spotter.com / driver123')