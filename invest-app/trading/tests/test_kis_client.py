from django.test import TestCase
from unittest.mock import patch
from trading.kis_client import KISApiClient
import io

class KISApiClientTest(TestCase):
    def setUp(self):
        # Mock API keys for testing
        self.client = KISApiClient(
            app_key="test_app_key",
            app_secret="test_app_secret",
            account_no="12345678-01",
            account_type='SIM'
        )

    @patch('builtins.open')
    def test_get_all_stock_codes(self, mock_open):
        kospi_data = b'005930,Samsung Electronics\n000660,SK Hynix'
        kosdaq_data = b'035720,Kakao\n035420,Naver'

        def open_side_effect(path, mode):
            if 'kospi' in path:
                return io.BytesIO(kospi_data)
            elif 'kosdaq' in path:
                return io.BytesIO(kosdaq_data)
            return io.BytesIO(b'')

        mock_open.side_effect = open_side_effect

        all_stocks = self.client.get_all_stock_codes(mst_file_path='/tmp/kis_mst')

        # Check if the function returns a dictionary
        self.assertIsInstance(all_stocks, dict)

        # Check if the dictionary contains the expected stocks
        self.assertIn('005930', all_stocks)
        self.assertEqual(all_stocks['005930'], 'Samsung Electronics')
        self.assertIn('000660', all_stocks)
        self.assertEqual(all_stocks['000660'], 'SK Hynix')
        self.assertIn('035720', all_stocks)
        self.assertEqual(all_stocks['035720'], 'Kakao')
        self.assertIn('035420', all_stocks)
        self.assertEqual(all_stocks['035420'], 'Naver')

        # Check that 'open' was called for both files
        self.assertEqual(mock_open.call_count, 2)
