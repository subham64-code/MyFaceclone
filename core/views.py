from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .models import Post, Like, Comment, FriendRequest, Profile
import json


def home(request):
    if request.user.is_authenticated:
        posts = Post.objects.select_related('author', 'author__profile').prefetch_related(
            'likes', 'comments', 'comments__author'
        )
        # Suggest people to connect with (exclude current user and existing friends)
        suggestions = User.objects.exclude(id=request.user.id)[:6]
        user_liked_posts = set(
            Like.objects.filter(user=request.user).values_list('post_id', flat=True)
        )
        context = {
            'posts': posts,
            'suggestions': suggestions,
            'user_liked_posts': user_liked_posts,
        }
        return render(request, 'home/index.html', context)
    return render(request, 'home/landing.html')


def signup_view(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        birthday = request.POST.get('birthday', '')
        gender = request.POST.get('gender', '')

        if not email or not password or not first_name or not last_name:
            return render(request, 'home/landing.html', {
                'signup_error': 'Please fill in all required fields.'
            })

        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        # Profile is created automatically via signal
        login(request, user)
        return redirect('home')

    return redirect('home')


def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        try:
            user = User.objects.get(email=email)
            user = authenticate(request, username=user.username, password=password)
        except User.DoesNotExist:
            user = None

        if user:
            login(request, user)
            return redirect('home')
        return render(request, 'home/landing.html', {
            'login_error': 'Invalid email or password.'
        })

    return redirect('home')


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
@require_POST
def create_post(request):
    content = request.POST.get('content', '').strip()
    image = request.FILES.get('image')
    if content or image:
        post = Post.objects.create(
            author=request.user,
            content=content,
            image=image,
        )
    return redirect('home')


@login_required
@require_POST
def toggle_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    like, created = Like.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': post.like_count()})


@login_required
@require_POST
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    data = json.loads(request.body)
    content = data.get('content', '').strip()
    if content:
        comment = Comment.objects.create(
            author=request.user,
            post=post,
            content=content,
        )
        return JsonResponse({
            'id': comment.id,
            'author': comment.author.get_full_name() or comment.author.username,
            'content': comment.content,
            'created_at': comment.created_at.strftime('%b %d, %Y'),
        })
    return JsonResponse({'error': 'Empty comment'}, status=400)


@login_required
def profile_view(request, username=None):
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        profile_user = request.user

    profile, _ = Profile.objects.get_or_create(user=profile_user)
    posts = Post.objects.filter(author=profile_user).select_related('author')
    user_liked_posts = set(
        Like.objects.filter(user=request.user).values_list('post_id', flat=True)
    )

    # Friend request status
    friend_status = None
    if profile_user != request.user:
        req = FriendRequest.objects.filter(
            sender=request.user, receiver=profile_user
        ).first() or FriendRequest.objects.filter(
            sender=profile_user, receiver=request.user
        ).first()
        if req:
            friend_status = req.status
            if req.receiver == request.user and req.status == 'pending':
                friend_status = 'received'

    context = {
        'profile_user': profile_user,
        'profile': profile,
        'posts': posts,
        'user_liked_posts': user_liked_posts,
        'friend_status': friend_status,
    }
    return render(request, 'home/profile.html', context)


@login_required
@require_POST
def send_friend_request(request, user_id):
    receiver = get_object_or_404(User, id=user_id)
    if receiver != request.user:
        FriendRequest.objects.get_or_create(sender=request.user, receiver=receiver)
    return redirect('profile', username=receiver.username)


@login_required
@require_POST
def respond_friend_request(request, request_id):
    freq = get_object_or_404(FriendRequest, id=request_id, receiver=request.user)
    action = request.POST.get('action')
    if action == 'accept':
        freq.status = 'accepted'
        freq.save()
    elif action == 'reject':
        freq.status = 'rejected'
        freq.save()
    return redirect('home')
