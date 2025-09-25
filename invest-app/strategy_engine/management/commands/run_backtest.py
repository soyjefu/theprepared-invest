from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from datetime import datetime
from strategy_engine.backtest import Backtester

class Command(BaseCommand):
    help = 'Runs a backtest of the trading strategy for a given period with adjustable parameters.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username for whom to run the backtest.')
        parser.add_argument('start_date', type=str, help='Start date (YYYY-MM-DD).')
        parser.add_argument('end_date', type=str, help='End date (YYYY-MM-DD).')
        parser.add_argument('--capital', type=int, default=100_000_000, help='Initial capital.')
        # 전략 파라미터 추가
        parser.add_argument('--risk-per-trade', type=float, help='Max risk per trade (e.g., 0.01 for 1%).')
        parser.add_argument('--max-total-risk', type=float, help='Max total portfolio risk (e.g., 0.1 for 10%).')

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options['username'])
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d').date()

            if start_date >= end_date:
                self.stdout.write(self.style.ERROR("Start date must be before the end date."))
                return

            # 백테스터에 전달할 파라미터 딕셔너리 생성
            backtest_params = {
                'user': user,
                'start_date': start_date,
                'end_date': end_date,
                'initial_capital': options['capital'],
                'strategy_params': {}
            }

            # 커맨드 라인 인자로 받은 파라미터가 있으면 strategy_params에 추가
            if options['risk_per_trade'] is not None:
                backtest_params['strategy_params']['risk_per_trade'] = options['risk_per_trade']
            if options['max_total_risk'] is not None:
                backtest_params['strategy_params']['max_total_risk'] = options['max_total_risk']

            self.stdout.write(self.style.SUCCESS(f"Starting backtest for user '{user.username}'..."))
            self.stdout.write(f"Period: {start_date} to {end_date}")
            self.stdout.write(f"Initial Capital: {backtest_params['initial_capital']:,} KRW")
            if backtest_params['strategy_params']:
                self.stdout.write("Custom Strategy Parameters:")
                for key, value in backtest_params['strategy_params'].items():
                    self.stdout.write(f"  - {key}: {value}")


            backtester = Backtester(**backtest_params)
            report = backtester.run()

            # 리포트 출력 (나중에는 파일 저장 또는 웹 표시로 변경 가능)
            if report and "error" not in report:
                self.stdout.write(self.style.SUCCESS("\n--- Backtest Finished ---"))
                self.stdout.write(f"Final Portfolio Value: {report['final_value']:,.0f} KRW")
                self.stdout.write(f"CAGR: {report['cagr']}")
            else:
                self.stdout.write(self.style.ERROR("Backtest failed or produced no results."))

        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{options['username']}' not found."))
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"Invalid date format or argument. Please use YYYY-MM-DD. Error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An unexpected error occurred: {e}"))