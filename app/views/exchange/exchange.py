#coding = utf-8

import logging

from django.conf import settings
from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
import requests
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv(".env")

logger = logging.getLogger(__name__)

EXCHANGE_API_KEY = settings.EXCHANGE_API_KEY

currency_path = os.path.join(os.path.dirname(__file__), 'currencies.json')
currencies = json.load(open(currency_path, "r", encoding="utf-8"))


def get_exchange_rate(from_currency, to_currency):
    url = f'https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/pair/{from_currency}/{to_currency}'
    response = requests.get(url, timeout=5)
    data = response.json()
    if data['result'] == 'success':
        return data['conversion_rate']
    else:
        return Exception(data.get("error-type", "Unknown error"))

@login_required
@require_http_methods(["GET", "POST"])
def exchange_view(request):
    result = None
    template = 'exchange/exchange.html'
    if request.method == 'POST':
        from_currency = request.POST.get('from_currency')
        to_currency = request.POST.get('to_currency')
        amount = request.POST.get('amount')
        if not currencies.get(from_currency) or not currencies.get(to_currency):
            messages.error(request, "Invalid currency selection.")
            return render(request, template, {
                'currencies': currencies.values(),
            })
        try:
            amount = float(amount)
            rate = get_exchange_rate(from_currency, to_currency)
            if isinstance(rate, Exception):
                messages.error(request, rate.args[0])
            converted = amount * rate
            result = f"{amount} {from_currency} = {converted:.2f} {to_currency}"
        except Exception as e:
            logger.error("Currency conversion error: %s", e)
            messages.error(request, "An error occurred during conversion. Please try again.")
            result = "Unexpected error occurred. Please try again later."
        return render(request, template, {
            'currencies': currencies.values(),
            'from': currencies.get(from_currency),
            'to': currencies.get(to_currency),
            'result': result,
        })

    return render(request, template, {
        'currencies': currencies.values(),
    })
