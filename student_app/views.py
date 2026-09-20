from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .models import Material, Message, Notification, Profile, Result


def login_view(request):
	if request.user.is_authenticated:
		return redirect('dashboard')
	if request.method == 'POST':
		username = request.POST.get('username')
		password = request.POST.get('password')
		user = authenticate(request, username=username, password=password)
		if user:
			login(request, user)
			return redirect(request.GET.get('next', 'dashboard'))
		messages.error(request, 'Invalid username or password.')
	return render(request, 'registration/login.html')


def signup(request):
	form = UserCreationForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		user = form.save()
		Profile.objects.create(user=user)
		login(request, user)
		return redirect('dashboard')
	return render(request, 'registration/signup.html', {'form': form})


def logout_view(request):
	logout(request)
	return redirect('login')


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
	return render(request, 'results.html', {'results': request.user.results.all()})


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
