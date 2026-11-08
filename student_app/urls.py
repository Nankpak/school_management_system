from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('results/', views.results, name='results'),
    path('payment/', views.payment, name='payment'),
    path('payment/remita/return/<int:payment_id>/', views.remita_return, name='remita_return'),
    path('payment/<int:payment_id>/receipt/', views.payment_receipt, name='payment_receipt'),
    path('materials/', views.materials, name='materials'),
    path('materials/upload/', views.upload_material, name='upload_material'),
    path('notifications/', views.notifications, name='notifications'),
    path('messages/', views.messages_view, name='messages'),
    path('messages/compose/', views.compose_message, name='compose_message'),
    path('profile/', views.profile, name='profile'),
    path('password/change/', views.PasswordChangeWithMessageView.as_view(), name='password_change'),
    path('password/reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset.html'), name='password_reset'),
    path('password/reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('password/reset/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('password/reset/complete/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
]