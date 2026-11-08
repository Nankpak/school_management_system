"""Small Remita REST API client for generating and verifying school-fee RRRs."""

import hashlib
from decimal import Decimal
from urllib.parse import urlencode

import requests
from django.conf import settings



class RemitaError(Exception):
	"""Raised when Remita is unavailable or returns an unusable response."""


def _required_setting(name):
	value = getattr(settings, name, '').strip()
	if not value:
		raise RemitaError(f'Remita is not configured: {name} is missing.')
	return value


def _sha512(value):
	return hashlib.sha512(value.encode('utf-8')).hexdigest()


def _response_data(response):
	response.raise_for_status()
	try:
		data = response.json()
	except ValueError as exc:
		raise RemitaError('Remita returned an unreadable response.') from exc
	# Some Remita endpoints wrap their single response in a one-item list.
	if isinstance(data, list) and data:
		data = data[0]
	if not isinstance(data, dict):
		raise RemitaError('Remita returned an unexpected response.')
	return data


def checkout_url(rrr, return_url=''):
	"""Build the hosted Remita checkout link for an existing RRR."""
	merchant_id = _required_setting('REMITA_MERCHANT_ID')
	checkout_base = getattr(settings, 'REMITA_CHECKOUT_BASE_URL', 'https://demo.remita.net').rstrip('/')
	params = {'rrr': str(rrr), 'merchantId': merchant_id}
	if return_url:
		params['responseurl'] = return_url
	return f'{checkout_base}/remita/ecomm/finalize.reg?{urlencode(params)}'


def generate_rrr(payment, payer_name, payer_email, payer_phone, return_url):
	"""Create an RRR through Remita and return (RRR, hosted checkout URL)."""
	merchant_id = _required_setting('REMITA_MERCHANT_ID')
	api_key = _required_setting('REMITA_API_KEY')
	service_type_id = _required_setting('REMITA_SERVICE_TYPE_ID')
	api_base = getattr(settings, 'REMITA_API_BASE_URL', 'https://demo.remita.net').rstrip('/')
	amount = format(Decimal(payment.amount).quantize(Decimal('0.01')), '.2f')
	order_id = str(payment.order_id)

	# The legacy e-channels endpoint signs the merchant/service/order/amount tuple with SHA-512.
	signature = _sha512(merchant_id + service_type_id + order_id + amount + api_key)
	payload = {
		'serviceTypeId': service_type_id,
		'amount': amount,
		'orderId': order_id,
		'payerName': payer_name,
		'payerEmail': payer_email,
		'payerPhone': payer_phone,
		'description': f'School fees for {payer_name}',
	}
	url = f'{api_base}/remita/exapp/api/v1/send/api/echannelsvc/merchant/api/paymentinit'
	try:
		response = requests.post(
			url,
			json=payload,
			headers={
				'Content-Type': 'application/json',
				'Authorization': f'remitaConsumerKey={merchant_id},remitaConsumerToken={signature}',
			},
			timeout=20,
		)
		data = _response_data(response)
	except (requests.RequestException, RemitaError) as exc:
		raise RemitaError('Could not generate an RRR with Remita. Please try again later.') from exc

	rrr = data.get('RRR') or data.get('rrr')
	if not rrr or not str(rrr).isdigit() or len(str(rrr)) > 30:
		raise RemitaError(data.get('status') or data.get('message') or 'Remita did not return a valid RRR.')
	return str(rrr), checkout_url(rrr, return_url)


def verify_rrr(rrr):
	"""Query Remita directly; browser redirects are never treated as proof of payment."""
	merchant_id = _required_setting('REMITA_MERCHANT_ID')
	api_key = _required_setting('REMITA_API_KEY')
	api_base = getattr(settings, 'REMITA_API_BASE_URL', 'https://demo.remita.net').rstrip('/')
	request_id = str(rrr)
	signature = _sha512(request_id + api_key + merchant_id)
	url = f'{api_base}/remita/exapp/api/v1/send/api/echannelsvc/{merchant_id}/{rrr}/{signature}/status.reg'
	try:
		response = requests.get(url, timeout=20)
		data = _response_data(response)
	except (requests.RequestException, RemitaError) as exc:
		raise RemitaError('Could not verify this payment with Remita. Please try again later.') from exc

	# Remita's documented successful transaction response code is "00".
	status_codes = (data.get('status'), data.get('statuscode'), data.get('statusCode'), data.get('responseCode'))
	return data, any(str(code).strip() == '00' for code in status_codes if code is not None)
