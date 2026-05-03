from __future__ import annotations

from decimal import Decimal

import aiohttp


class CryptoPayService:
    def __init__(self, token: str | None, api_url: str):
        self.token = token
        self.api_url = api_url.rstrip('/')

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def create_invoice(self, amount: Decimal, payload: str) -> dict | None:
        if not self.enabled:
            return None
        headers = {'Crypto-Pay-API-Token': self.token}
        data = {
            'asset': 'USDT',
            'amount': str(amount),
            'description': 'Balance top up',
            'hidden_message': payload,
            'paid_btn_name': 'callback',
            'paid_btn_url': 'https://t.me/',
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f'{self.api_url}/createInvoice', json=data, headers=headers) as response:
                result = await response.json()
                if result.get('ok'):
                    return result.get('result')
        return None

    async def get_invoice(self, invoice_id: str) -> dict | None:
        if not self.enabled:
            return None
        headers = {'Crypto-Pay-API-Token': self.token}
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self.api_url}/getInvoices?invoice_ids={invoice_id}', headers=headers) as response:
                result = await response.json()
                if result.get('ok'):
                    items = result.get('result', {}).get('items', [])
                    return items[0] if items else None
        return None
