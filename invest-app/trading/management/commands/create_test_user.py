from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import os

class Command(BaseCommand):
    help = 'Creates a test superuser for development and testing.'

    def handle(self, *args, **options):
        username = 'testuser'
        password = 'testpassword123'
        email = 'test@example.com'

        if not User.objects.filter(username=username).exists():
            self.stdout.write(f'Creating account for {username}')
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f'Successfully created superuser: {username}'))
        else:
            self.stdout.write(self.style.WARNING(f'User {username} already exists. Skipping creation.'))
