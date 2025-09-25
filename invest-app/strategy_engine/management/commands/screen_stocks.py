from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from strategy_engine.services import UniverseScreener
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the stock screening process to update the investment universe.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username of the user whose account will be used.')
        parser.add_argument('--account', type=str, help='Optional: The specific account number to use.', default=None)

    def handle(self, *args, **options):
        username = options['username']
        account_number = options['account']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' not found."))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting stock screening for user '{username}'..."))

        try:
            screener = UniverseScreener(user=user, account_number=account_number)
            screened_count = screener.screen_all_stocks()
            self.stdout.write(self.style.SUCCESS(f"Screening complete. {screened_count} stocks were added/updated in the universe."))
        except Exception as e:
            logger.error(f"An error occurred during the screening process: {e}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"An error occurred: {e}"))