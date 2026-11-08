from django.conf import settings
from django.db import models
import uuid


def new_payment_order_id():
	"""Generate a UUID order ID not already present in the payment table."""
	return uuid.uuid4()


class Profile(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
	phone = models.CharField(max_length=30, blank=True)
	programme = models.CharField(max_length=120, blank=True)
	level = models.CharField(max_length=50, blank=True)
	date_of_birth = models.DateField(null=True, blank=True)
	address = models.TextField(blank=True)
	photo = models.ImageField(upload_to='profiles/', blank=True, null=True)

	def __str__(self):
		return f'{self.user.get_full_name() or self.user.username} profile'


class Result(models.Model):
	student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='results')
	course_code = models.CharField(max_length=20)
	course_title = models.CharField(max_length=150)
	score = models.PositiveIntegerField()
	grade = models.CharField(max_length=3)
	semester = models.CharField(max_length=50)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['course_code']

	def __str__(self):
		return f'{self.student.username} - {self.course_code}'


class SchoolFeePayment(models.Model):
	PAYMENT_METHODS = [
		('bank_card', 'Bank card'),
		('bank_transfer', 'Bank transfer'),
		('other', 'Other'),
	]
	PAYMENT_STATUSES = [
		('pending', 'Pending Remita payment'),
		('paid', 'Paid'),
		('rejected', 'Rejected'),
	]
	student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='school_fee_payments')
	amount = models.DecimalField(max_digits=10, decimal_places=2)
	payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='bank_card')
	status = models.CharField(max_length=10, choices=PAYMENT_STATUSES, default='pending')
	# Store the Remita reference and our immutable request id for callback verification.
	rrr = models.CharField(max_length=30, unique=True, null=True, blank=True)
	order_id = models.UUIDField(default=new_payment_order_id, editable=False)
	bank_name = models.CharField(max_length=80, default='Opay Bank')
	account_number = models.CharField(max_length=20, default='9129560631')
	reference = models.CharField(max_length=100, blank=True, default='')
	created_at = models.DateTimeField(auto_now_add=True)
	verified_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ['-created_at']
		constraints = [models.UniqueConstraint(fields=['order_id'], name='unique_school_fee_order_id')]

	def __str__(self):
		return f'{self.student.username} - {self.amount} ({self.status})'


class Material(models.Model):
	title = models.CharField(max_length=180)
	description = models.TextField(blank=True)
	file = models.FileField(upload_to='materials/')
	uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='materials')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-created_at']


class Notification(models.Model):
	title = models.CharField(max_length=180)
	message = models.TextField()
	created_at = models.DateTimeField(auto_now_add=True)
	is_read = models.BooleanField(default=False)

	class Meta:
		ordering = ['-created_at']


class Message(models.Model):
	sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
	recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
	subject = models.CharField(max_length=180)
	body = models.TextField()
	created_at = models.DateTimeField(auto_now_add=True)
	is_read = models.BooleanField(default=False)

	class Meta:
		ordering = ['-created_at']
