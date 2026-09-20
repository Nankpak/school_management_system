from django.contrib import admin
from .models import Material, Message, Notification, Profile, Result


admin.site.register([Profile, Result, Material, Notification, Message])
