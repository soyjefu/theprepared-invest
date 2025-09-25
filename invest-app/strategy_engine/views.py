from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import datetime
from decimal import Decimal
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from .backtest import Backtester

@login_required
def backtest_view(request):
    context = {'report': None}
    if request.method == 'POST':
        try:
            start_date = datetime.strptime(request.POST.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.POST.get('end_date'), '%Y-%m-%d').date()
            initial_capital = Decimal(request.POST.get('initial_capital', '100000000'))

            # TODO: 폼에서 더 많은 전략 파라미터를 받을 수 있도록 확장 가능
            strategy_params = {}

            backtester = Backtester(
                user=request.user,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                strategy_params=strategy_params
            )
            report = backtester.run()

            if report and "error" not in report:
                # Plotly 그래프 생성
                daily_values = report['daily_values']
                if daily_values:
                    df = pd.DataFrame(daily_values)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=df['date'], y=df['value'], mode='lines', name='Portfolio Value'))
                    fig.update_layout(
                        title='Portfolio Value Over Time',
                        xaxis_title='Date',
                        yaxis_title='Portfolio Value (KRW)'
                    )
                    # 그래프를 HTML div로 변환
                    plot_div = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')
                    context['plot_div'] = plot_div

                context['report'] = report

        except Exception as e:
            context['error'] = f"An error occurred: {e}"

    return render(request, 'strategy_engine/backtest_report.html', context)
