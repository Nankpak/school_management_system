from django.contrib import admin
from .models import Material, Message, Notification, Profile, Result, SchoolFeePayment


@admin.register(SchoolFeePayment)
class SchoolFeePaymentAdmin(admin.ModelAdmin):
	list_display = ('student', 'amount', 'payment_method', 'status', 'rrr', 'reference', 'created_at')
	list_filter = ('status', 'payment_method', 'created_at')
	search_fields = ('student__username', 'student__email', 'rrr', 'reference', 'order_id')
	readonly_fields = ('student', 'amount', 'payment_method', 'rrr', 'order_id', 'bank_name', 'account_number', 'reference', 'created_at')

	def save_model(self, request, obj, form, change):
		# Only staff can mark a payment paid; the student submission never sets status.
		if obj.status == 'paid' and not obj.verified_at:
			from django.utils import timezone
			obj.verified_at = timezone.now()
		super().save_model(request, obj, form, change)


admin.site.register([Profile, Result, Material, Notification, Message])
