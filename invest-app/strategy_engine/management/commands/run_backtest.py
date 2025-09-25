from django.core.management.base import BaseCommand
from datetime import datetime
from strategy_engine.backtest import Backtester

class Command(BaseCommand):
    help = 'Runs a backtest of the trading strategy for a given period.'

    def add_arguments(self, parser):
        parser.add_argument('start_date', type=str, help='Start date for the backtest in YYYY-MM-DD format.')
        parser.add_argument('end_date', type=str, help='End date for the backtest in YYYY-MM-DD format.')
        parser.add_argument('--capital', type=int, default=100000000, help='Initial capital for the backtest (default: 100,000,000).')

    def handle(self, *args, **options):
        try:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d').date()
            initial_capital = options['capital']

            if start_date >= end_date:
                self.stdout.write(self.style.ERROR("Start date must be before the end date."))
                return

            self.stdout.write(self.style.SUCCESS(
                f"Starting backtest from {start_date} to {end_date} with initial capital of {initial_capital:,} KRW."
            ))

            backtester = Backtester(start_date=start_date, end_date=end_date, initial_capital=initial_capital)
            backtester.run()

            self.stdout.write(self.style.SUCCESS("Backtest finished."))

        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"Invalid date format or argument. Please use YYYY-MM-DD. Error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An unexpected error occurred during the backtest: {e}"))