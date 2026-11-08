from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.conf import settings
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from .models import Material, Message, Notification, Profile, Result, SchoolFeePayment
from .remita import RemitaError, checkout_url, generate_rrr, verify_rrr


def login_view(request):
	if request.user.is_authenticated:
		return redirect('dashboard')
	if request.method == 'POST':
		username = request.POST.get('username')
		password = request.POST.get('password')
		user = authenticate(request, username=username, password=password)
		if user:
			login(request, user)
			messages.success(request, 'You have signed in successfully.')
			return redirect(request.GET.get('next', 'dashboard'))
		messages.error(request, 'Invalid username or password. Please try again.')
	return render(request, 'registration/login.html')


class SignupForm(UserCreationForm):
	email = forms.EmailField(required=True, label='Email address')

	class Meta(UserCreationForm.Meta):
		fields = ('username', 'email', 'password1', 'password2')

	def save(self, commit=True):
		user = super().save(commit=False)
		user.email = self.cleaned_data['email']
		if commit:
			user.save()
		return user


def signup(request):
	form = SignupForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		user = form.save()
		Profile.objects.create(user=user)
		login(request, user)
		messages.success(request, 'Your account was created successfully. Welcome to CampusDesk!')
		return redirect('dashboard')
	return render(request, 'registration/signup.html', {'form': form})


def logout_view(request):
	logout(request)
	messages.success(request, 'You have signed out successfully.')
	return redirect('login')


class PasswordChangeWithMessageView(PasswordChangeView):
	template_name = 'registration/password_change.html'
	success_url = reverse_lazy('profile')

	def form_valid(self, form):
		response = super().form_valid(form)
		messages.success(self.request, 'Your password was changed successfully.')
		return response


@login_required
def dashboard(request):
	profile, _ = Profile.objects.get_or_create(user=request.user)
	context = {
		'profile': profile,
		'result_count': request.user.results.count(),
		'material_count': Material.objects.count(),
		'unread_messages': request.user.received_messages.filter(is_read=False).count(),
		'notifications': Notification.objects.all()[:4],
		'recent_materials': Material.objects.all()[:5],
	}
	return render(request, 'dashboard.html', context)


@login_required
def results(request):
	# Only an administrator-verified payment unlocks academic results.
	if not request.user.school_fee_payments.filter(status='paid').exists():
		messages.info(request, 'Pay your school fee through Remita to access results.')
		return redirect('payment')
	return render(request, 'results.html', {'results': request.user.results.all()})


@login_required
def payment(request):
	paid_payment = request.user.school_fee_payments.filter(status='paid').first()
	if paid_payment:
		return redirect('payment_receipt', payment_id=paid_payment.pk)

	amount = getattr(settings, 'SCHOOL_FEE_AMOUNT', 0)
	latest_payment = request.user.school_fee_payments.first()
	resume_checkout_url = ''
	if latest_payment and latest_payment.rrr and latest_payment.status == 'pending':
		try:
			callback_url = request.build_absolute_uri(reverse('remita_return', args=[latest_payment.pk]))
			resume_checkout_url = checkout_url(latest_payment.rrr, callback_url)
		except RemitaError as exc:
			messages.error(request, str(exc))

	if request.method == 'POST':
		method = request.POST.get('payment_method', 'bank_card')
		if not amount or amount <= 0:
			messages.error(request, 'The school has not configured the fee amount yet. Please contact the administration.')
		elif method not in dict(SchoolFeePayment.PAYMENT_METHODS):
			messages.error(request, 'Choose a valid payment method.')
		else:
			profile, _ = Profile.objects.get_or_create(user=request.user)
			payer_email = request.user.email.strip()
			payer_phone = profile.phone.strip()
			if not payer_email or not payer_phone:
				messages.error(request, 'Add your email and phone number to your profile before paying with Remita.')
			else:
				# The server chooses the configured fee amount; never trust a browser-sent amount.
				payment_record = SchoolFeePayment.objects.create(
				student=request.user,
				amount=amount,
				payment_method=method,
				)
				try:
					callback_url = request.build_absolute_uri(reverse('remita_return', args=[payment_record.pk]))
					rrr, hosted_checkout = generate_rrr(
						payment_record,
						request.user.get_full_name() or request.user.username,
						payer_email,
						payer_phone,
						callback_url,
					)
				except RemitaError as exc:
					# Keep the failed attempt for an audit trail, but allow a fresh attempt.
					payment_record.status = 'rejected'
					payment_record.reference = str(exc)[:100]
					payment_record.save(update_fields=['status', 'reference'])
					messages.error(request, str(exc))
				else:
					payment_record.rrr = rrr
					payment_record.save(update_fields=['rrr'])
					return redirect(hosted_checkout)

	return render(request, 'payment.html', {
		'fee_amount': amount,
		'latest_payment': latest_payment,
		'checkout_url': resume_checkout_url,
	})


@login_required
def remita_return(request, payment_id):
	"""Verify the RRR with Remita before marking it paid and releasing a receipt."""
	payment_record = get_object_or_404(SchoolFeePayment, pk=payment_id, student=request.user)
	if payment_record.status == 'paid':
		return redirect('payment_receipt', payment_id=payment_record.pk)
	if not payment_record.rrr:
		messages.error(request, 'This payment does not have a Remita RRR to verify.')
		return redirect('payment')

	try:
		data, is_paid = verify_rrr(payment_record.rrr)
	except RemitaError as exc:
		messages.error(request, str(exc))
		return redirect('payment')

	# Check the paid amount when Remita includes it; a partial payment is not accepted.
	paid_amount = data.get('amountPaid') or data.get('amount')
	returned_rrr = data.get('RRR') or data.get('rrr')
	if is_paid and returned_rrr and str(returned_rrr) != payment_record.rrr:
		is_paid = False
	if is_paid and paid_amount is None:
		# Do not release results or a receipt unless Remita confirms the exact amount.
		is_paid = False
	elif is_paid:
		try:
			is_paid = Decimal(str(paid_amount)).quantize(Decimal('0.01')) == payment_record.amount
		except (InvalidOperation, TypeError, ValueError):
			is_paid = False

	if not is_paid:
		messages.info(request, 'Remita has not confirmed the full payment yet. Your RRR remains available for payment.')
		return redirect('payment')

	payment_record.status = 'paid'
	payment_record.verified_at = timezone.now()
	payment_record.reference = str(data.get('transactionId') or data.get('transactionRef') or '')[:100]
	payment_record.save(update_fields=['status', 'verified_at', 'reference'])
	messages.success(request, 'Payment confirmed. Your receipt download is ready.')
	return redirect('payment_receipt', payment_id=payment_record.pk)


@login_required
def payment_receipt(request, payment_id):
	"""Download a receipt only after Remita has confirmed the payment."""
	payment_record = get_object_or_404(SchoolFeePayment, pk=payment_id, student=request.user)
	if payment_record.status != 'paid':
		messages.error(request, 'A receipt is available only after Remita confirms payment.')
		return redirect('payment')

	lines = [
		'CampusDesk - School Fee Payment Receipt',
		'========================================',
		f'Student: {request.user.get_full_name() or request.user.username}',
		f'Amount: NGN {payment_record.amount:.2f}',
		f'Payment method: {payment_record.get_payment_method_display()}',
		f'Remita Retrieval Reference (RRR): {payment_record.rrr}',
		f'Remita transaction reference: {payment_record.reference or "Not provided"}',
		f'Payment verified: {payment_record.verified_at:%Y-%m-%d %H:%M UTC}',
		'Payment status: PAID',
	]
	response = HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')
	response['Content-Disposition'] = f'attachment; filename="school-fee-receipt-{payment_record.rrr}.txt"'
	return response


@login_required
def materials(request):
	return render(request, 'materials.html', {'materials': Material.objects.all()})


@login_required
def upload_material(request):
	if request.method == 'POST' and request.FILES.get('file'):
		Material.objects.create(
			title=request.POST.get('title', 'Untitled material'),
			description=request.POST.get('description', ''),
			file=request.FILES['file'],
			uploaded_by=request.user,
		)
		messages.success(request, 'Lecture material uploaded successfully.')
	return redirect('materials')


@login_required
def notifications(request):
	items = Notification.objects.all()
	items.update(is_read=True)
	return render(request, 'notifications.html', {'notifications': items})


@login_required
def messages_view(request):
	received = request.user.received_messages.select_related('sender')
	sent = request.user.sent_messages.select_related('recipient')
	received.update(is_read=True)
	return render(request, 'messages.html', {'received': received, 'sent': sent})


@login_required
def compose_message(request):
	users = User.objects.exclude(pk=request.user.pk).order_by('username')
	if request.method == 'POST':
		recipient = get_object_or_404(User, pk=request.POST.get('recipient'))
		Message.objects.create(sender=request.user, recipient=recipient, subject=request.POST.get('subject', ''), body=request.POST.get('body', ''))
		messages.success(request, 'Message sent.')
		return redirect('messages')
	return render(request, 'compose_message.html', {'users': users})


@login_required
def profile(request):
	profile, _ = Profile.objects.get_or_create(user=request.user)
	if request.method == 'POST':
		request.user.first_name = request.POST.get('first_name', '').strip()
		request.user.last_name = request.POST.get('last_name', '').strip()
		request.user.email = request.POST.get('email', '').strip()
		request.user.save()
		for field in ('phone', 'programme', 'level', 'date_of_birth', 'address'):
			setattr(profile, field, request.POST.get(field, ''))
		if request.POST.get('delete_photo') and profile.photo:
			profile.photo.delete(save=False)
			profile.photo = None
		elif request.FILES.get('photo'):
			profile.photo = request.FILES['photo']
		profile.save()
		messages.success(request, 'Your profile has been updated.')
		return redirect('profile')
	return render(request, 'profile.html', {'profile': profile})
