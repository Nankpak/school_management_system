from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Profile, SchoolFeePayment
from .remita import generate_rrr, verify_rrr


class RegistrationTests(TestCase):
	def test_signup_form_accepts_email_and_saves_it(self):
		response = self.client.post(reverse('signup'), {
			'username': 'newstudent',
			'email': 'newstudent@example.com',
			'password1': 'StrongPass123',
			'password2': 'StrongPass123',
		})
		self.assertEqual(response.status_code, 302)
		user = User.objects.get(username='newstudent')
		self.assertEqual(user.email, 'newstudent@example.com')
		self.assertTrue(Profile.objects.filter(user=user).exists())


class PaymentGateTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='student1', password='StrongPass123', email='student@example.com',
		)
		Profile.objects.create(user=self.user, phone='08012345678')
		self.client.login(username='student1', password='StrongPass123')

	def test_unpaid_student_cannot_view_results(self):
		response = self.client.get(reverse('results'))
		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, reverse('payment'))

	def test_paid_student_can_view_results(self):
		SchoolFeePayment.objects.create(
			student=self.user,
			amount=15000,
			payment_method='bank_card',
			status='paid',
			bank_name='Opay Bank',
			account_number='9129560631',
			reference='REF-001',
		)

		response = self.client.get(reverse('results'))
		self.assertEqual(response.status_code, 200)

	@patch('student_app.views.generate_rrr', return_value=('123456789012', 'https://remitademo.net/checkout'))
	def test_student_choice_generates_rrr_and_redirects_to_remita(self, generate):
		with self.settings(SCHOOL_FEE_AMOUNT=Decimal('15000.00')):
			response = self.client.post(reverse('payment'), {
				'payment_method': 'bank_transfer',
			})

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], 'https://remitademo.net/checkout')
		payment = SchoolFeePayment.objects.get(student=self.user)
		self.assertEqual(payment.status, 'pending')
		self.assertEqual(payment.amount, Decimal('15000.00'))
		self.assertEqual(payment.payment_method, 'bank_transfer')
		self.assertEqual(payment.rrr, '123456789012')
		generate.assert_called_once()

		response = self.client.get(reverse('results'))
		self.assertRedirects(response, reverse('payment'))

	@patch('student_app.views.verify_rrr', return_value=({'status': '00', 'amountPaid': '15000.00', 'transactionId': 'TX-001'}, True))
	@patch('student_app.views.generate_rrr', return_value=('123456789012', 'https://remitademo.net/checkout'))
	def test_remita_confirmation_redirects_to_downloadable_receipt(self, generate, verify):
		with self.settings(SCHOOL_FEE_AMOUNT=Decimal('15000.00')):
			self.client.post(reverse('payment'), {
				'payment_method': 'bank_card',
			})
		payment = SchoolFeePayment.objects.get(student=self.user)
		response = self.client.get(reverse('remita_return', args=[payment.pk]))

		self.assertRedirects(response, reverse('payment_receipt', args=[payment.pk]))
		payment.refresh_from_db()
		self.assertEqual(payment.status, 'paid')
		self.assertEqual(payment.reference, 'TX-001')
		verify.assert_called_once_with('123456789012')

		receipt = self.client.get(reverse('payment_receipt', args=[payment.pk]))
		self.assertEqual(receipt.status_code, 200)
		self.assertIn('attachment;', receipt['Content-Disposition'])
		self.assertContains(receipt, '123456789012')
		self.assertContains(receipt, 'NGN 15000.00')

		self.assertEqual(self.client.get(reverse('results')).status_code, 200)

	@patch('student_app.views.verify_rrr', return_value=({'status': '01'}, False))
	@patch('student_app.views.generate_rrr', return_value=('123456789012', 'https://remitademo.net/checkout'))
	def test_unconfirmed_or_underpaid_remita_status_does_not_unlock_results(self, generate, verify):
		with self.settings(SCHOOL_FEE_AMOUNT=Decimal('15000.00')):
			self.client.post(reverse('payment'), {'payment_method': 'bank_card'})
		payment = SchoolFeePayment.objects.get(student=self.user)
		self.client.get(reverse('remita_return', args=[payment.pk]))

		payment.refresh_from_db()
		self.assertEqual(payment.status, 'pending')
		verify.return_value = ({'statuscode': '00', 'amountPaid': '14999.00'}, True)
		self.client.get(reverse('remita_return', args=[payment.pk]))
		payment.refresh_from_db()
		self.assertEqual(payment.status, 'pending')
		self.assertRedirects(self.client.get(reverse('results')), reverse('payment'))

	@patch('student_app.views.generate_rrr')
	def test_invalid_payment_method_is_rejected(self, generate):
		with self.settings(SCHOOL_FEE_AMOUNT=15000):
			self.client.post(reverse('payment'), {'payment_method': 'cash-in-browser'})
		self.assertEqual(SchoolFeePayment.objects.count(), 0)
		generate.assert_not_called()

	def test_payment_page_shows_default_fee_and_remita_channel(self):
		response = self.client.get(reverse('payment'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '50000.00')
		self.assertContains(response, 'Generate RRR and continue')
		self.assertContains(response, 'bank transfer')
		self.assertContains(response, 'Remita')

	@patch('student_app.views.verify_rrr')
	def test_student_cannot_download_another_students_receipt(self, verify):
		other_user = User.objects.create_user(username='student2', password='StrongPass123')
		payment = SchoolFeePayment.objects.create(
			student=other_user,
			amount=15000,
			status='paid',
			rrr='987654321098',
		)
		response = self.client.get(reverse('payment_receipt', args=[payment.pk]))
		self.assertEqual(response.status_code, 404)
		verify.assert_not_called()


class RemitaClientTests(TestCase):
	@override_settings(
		REMITA_MERCHANT_ID='merchant-test',
		REMITA_API_KEY='secret-test-key',
		REMITA_SERVICE_TYPE_ID='service-test',
		REMITA_API_BASE_URL='https://remitademo.net',
		REMITA_CHECKOUT_BASE_URL='https://remitademo.net',
	)
	@patch('student_app.remita.requests.post')
	def test_rrr_request_is_signed_and_uses_configured_amount(self, post):
		response = post.return_value
		response.json.return_value = {'RRR': '123456789012'}
		payment = type('PaymentDetails', (), {'amount': Decimal('15000.00'), 'order_id': uuid4()})()

		rrr, hosted_url = generate_rrr(
			payment,
			'Example Student',
			'student@example.com',
			'08012345678',
			'https://school.test/payment/remita/return/4/',
		)

		self.assertEqual(rrr, '123456789012')
		self.assertIn('rrr=123456789012', hosted_url)
		self.assertIn('responseurl=', hosted_url)
		args, kwargs = post.call_args
		self.assertEqual(args[0], 'https://remitademo.net/remita/exapp/api/v1/send/api/echannelsvc/merchant/api/paymentinit')
		self.assertEqual(kwargs['json']['amount'], '15000.00')
		self.assertEqual(kwargs['json']['serviceTypeId'], 'service-test')
		self.assertTrue(kwargs['headers']['Authorization'].startswith('remitaConsumerKey=merchant-test,remitaConsumerToken='))

	@override_settings(
		REMITA_MERCHANT_ID='merchant-test',
		REMITA_API_KEY='secret-test-key',
		REMITA_API_BASE_URL='https://remitademo.net',
	)
	@patch('student_app.remita.requests.get')
	def test_remita_status_only_accepts_explicit_success_code(self, get):
		get.return_value.json.return_value = {'status': 'Successful', 'statuscode': '00'}
		data, is_paid = verify_rrr('123456789012')
		self.assertEqual(data['statuscode'], '00')
		self.assertTrue(is_paid)

		get.return_value.json.return_value = {'status': 'Successful'}
		_, is_paid = verify_rrr('123456789012')
		self.assertFalse(is_paid)

		get.return_value.json.return_value = {'statuscode': '00', 'amountPaid': '15000.00'}
		_, is_paid = verify_rrr('123456789012')
		self.assertTrue(is_paid)
