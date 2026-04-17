import json

from django.contrib import messages
from asgiref.sync import async_to_sync
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from datetime import timedelta
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    BlockedUser,
    COUNTRY_CHOICES,
    ChatGroup,
    ChatGroupMember,
    Follow,
    Friendship,
    GroupMessage,
    Message,
    Notification,
    PostComment,
    PostLike,
    SavedPost,
    Story,
    UserPost,
)


SENSITIVE_PATTERNS = (
    "spam",
    "scam",
    "phish",
    "hate",
    "abuse",
)


def _sanitize_text(text):
    lowered = text.lower()
    for pattern in SENSITIVE_PATTERNS:
        if pattern in lowered:
            return ""
    return text


def _extract_tags(posts):
    tag_scores = {}
    for post in posts:
        for token in (post.post or "").split():
            if token.startswith("#") and len(token) > 1:
                tag_scores[token.lower()] = tag_scores.get(token.lower(), 0) + 1
    return tag_scores


def _recommended_people(user, blocked_ids, friend_ids):
    user_country = user.userprofile.country
    friend_id_set = set(friend_ids)

    def mutual_friend_count(candidate_id):
        candidate_friend_ids = set(
            Friendship.objects.filter(status=Friendship.STATUS_ACCEPTED)
            .filter(Q(from_user_id=candidate_id) | Q(to_user_id=candidate_id))
            .values_list("from_user_id", "to_user_id")
        )
        flattened = set()
        for left_id, right_id in candidate_friend_ids:
            if left_id != candidate_id:
                flattened.add(left_id)
            if right_id != candidate_id:
                flattened.add(right_id)
        flattened.discard(user.id)
        return len(flattened.intersection(friend_id_set))

    engaged_user_ids = set(
        list(Follow.objects.filter(follower=user).values_list("following_id", flat=True))
        + list(PostLike.objects.filter(user=user).values_list("post__user_id", flat=True))
        + list(PostComment.objects.filter(user=user).values_list("post__user_id", flat=True))
    )
    candidates = (
        User.objects.exclude(id__in=list(blocked_ids) + [user.id] + list(friend_ids))
        .annotate(
            followers_count=Count("follower_set", distinct=True),
            posts_count=Count("userpost", distinct=True),
        )
        .order_by("-followers_count", "-posts_count", "username")[:12]
    )
    ranked = sorted(
        candidates,
        key=lambda person: (
            1 if person.id in engaged_user_ids else 0,
            1 if user_country and person.userprofile.country == user_country else 0,
            mutual_friend_count(person.id),
            person.followers_count,
            person.posts_count,
            person.username.lower(),
        ),
        reverse=True,
    )
    recommended = []
    for person in ranked[:6]:
        reasons = []
        if person.id in engaged_user_ids:
            reasons.append("based on your activity")
        if user_country and person.userprofile.country == user_country:
            reasons.append("same country")
        mutual_count = mutual_friend_count(person.id)
        if mutual_count:
            reasons.append(f"{mutual_count} mutual friends")
        person.recommendation_reason = ", ".join(reasons) if reasons else "popular in your network"
        recommended.append(person)
    return recommended


def _recommended_posts(user, visible_user_ids):
    followed_ids = set(Follow.objects.filter(follower=user).values_list("following_id", flat=True))
    liked_posts = UserPost.objects.filter(likes__user=user).only("post")
    interests = _extract_tags(liked_posts)
    user_country = user.userprofile.country
    posts = _ranked_posts_queryset(user, visible_user_ids)
    scored = []
    for post in posts:
        score = 0
        if post.user_id in followed_ids:
            score += 6
        if user_country and getattr(post.user, "userprofile", None) and post.user.userprofile.country == user_country:
            score += 3
        if post.user_id == user.id:
            score += 2
        for token in (post.post or "").split():
            if token.lower() in interests:
                score += interests[token.lower()] * 4
        score += min(5, getattr(post, "like_count", 0))
        score += min(5, getattr(post, "comment_count", 0)) * 2
        scored.append((score, post))
    scored.sort(key=lambda item: item[0], reverse=True)
    recommended_posts = []
    for score, post in scored[:8]:
        reasons = []
        if post.user_id in followed_ids:
            reasons.append("from people you follow")
        if user_country and post.user.userprofile.country == user_country:
            reasons.append("same country")
        if getattr(post, "like_count", 0) or getattr(post, "comment_count", 0):
            reasons.append("trending engagement")
        post.recommendation_reason = ", ".join(reasons) if reasons else "for your feed"
        post.recommendation_score = score
        recommended_posts.append(post)
    return recommended_posts


def _accepted_friend_ids(user):
    sent = Friendship.objects.filter(from_user=user, status=Friendship.STATUS_ACCEPTED).values_list("to_user_id", flat=True)
    received = Friendship.objects.filter(to_user=user, status=Friendship.STATUS_ACCEPTED).values_list("from_user_id", flat=True)
    return set(sent).union(set(received))


def _friendship_between(user_a, user_b):
    return Friendship.objects.filter(
        Q(from_user=user_a, to_user=user_b) | Q(from_user=user_b, to_user=user_a)
    ).first()


def _blocked_user_ids(user):
    blocked_by_me = BlockedUser.objects.filter(user=user).values_list("blocked_user_id", flat=True)
    blocked_me = BlockedUser.objects.filter(blocked_user=user).values_list("user_id", flat=True)
    return set(blocked_by_me).union(set(blocked_me))


def _push_notification(recipient, actor, notif_type, text, link=""):
    if recipient == actor:
        return
    notif = Notification.objects.create(
        recipient=recipient,
        actor=actor,
        type=notif_type,
        text=text,
        link=link,
    )
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{recipient.id}",
        {
            "type": "notify.event",
            "payload": {
                "id": notif.id,
                "text": notif.text,
                "actor": actor.username,
                "link": notif.link,
            },
        },
    )


def _ranked_posts_queryset(user, visible_user_ids):
    age_seconds_expr = timezone.now().timestamp()
    posts = (
        UserPost.objects.filter(user_id__in=visible_user_ids)
        .select_related("user", "user__userprofile")
        .prefetch_related("likes", "comments", "comments__user")
        .annotate(like_count=Count("likes", distinct=True), comment_count=Count("comments", distinct=True))
    )

    ranked = sorted(
        posts,
        key=lambda p: (
            (p.like_count * 2 + p.comment_count * 3)
            + max(0, int(86400 - (age_seconds_expr - p.date.timestamp())) / 3600)
        ),
        reverse=True,
    )
    return ranked


def index(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        pwd = request.POST.get("password", "")
        user = authenticate(username=username, password=pwd)
        if user is not None:
            login(request, user)
            return redirect("home")
        messages.error(request, "Invalid username or password.")

    return render(request, "index.html", {"country_choices": COUNTRY_CHOICES})


@login_required(login_url="index")
def home(request):
    user = request.user
    friend_ids = _accepted_friend_ids(user)
    blocked_ids = _blocked_user_ids(user)

    public_user_ids = set(
        User.objects.filter(userprofile__is_private=False).exclude(id__in=blocked_ids).values_list("id", flat=True)
    )
    visible_user_ids = set(friend_ids).union({user.id}).union(public_user_ids)
    visible_user_ids = list(visible_user_ids.difference(blocked_ids))

    posts = _ranked_posts_queryset(user, visible_user_ids)
    posts = [
        p for p in posts
        if p.visibility == UserPost.VISIBILITY_PUBLIC
        or p.user_id == user.id
        or (p.visibility == UserPost.VISIBILITY_FRIENDS and p.user_id in friend_ids)
    ]

    query = request.GET.get("q", "").strip()
    search_results = []
    if query:
        search_results = User.objects.filter(username__icontains=query).exclude(id=user.id).exclude(id__in=blocked_ids)[:10]

    pending_requests = Friendship.objects.filter(
        to_user=user,
        status=Friendship.STATUS_PENDING,
    ).select_related("from_user")

    suggestions = (
        User.objects.exclude(id__in=list(friend_ids) + [user.id] + list(blocked_ids))
        .exclude(username="")
        .order_by("username")[:8]
    )
    ai_people = _recommended_people(user, blocked_ids, friend_ids)
    ai_posts = _recommended_posts(user, visible_user_ids)

    liked_post_ids = set(
        PostLike.objects.filter(user=user, post__in=posts).values_list("post_id", flat=True)
    )
    saved_post_ids = set(
        SavedPost.objects.filter(user=user, post__in=posts).values_list("post_id", flat=True)
    )
    stories = Story.objects.filter(expires_at__gt=timezone.now(), user_id__in=visible_user_ids).select_related("user")
    unread_notifications = Notification.objects.filter(recipient=user, is_read=False).count()
    following_ids = set(Follow.objects.filter(follower=user).values_list("following_id", flat=True))

    context = {
        "posts": posts,
        "pending_requests": pending_requests,
        "suggestions": suggestions,
        "liked_post_ids": liked_post_ids,
        "friend_count": len(friend_ids),
        "query": query,
        "search_results": search_results,
        "saved_post_ids": saved_post_ids,
        "stories": stories,
        "unread_notifications": unread_notifications,
        "following_ids": following_ids,
        "ai_people": ai_people,
        "ai_posts": ai_posts,
        "country_choices": COUNTRY_CHOICES,
    }
    return render(request, "home.html", context)


@login_required(login_url="index")
def explore(request):
    blocked_ids = _blocked_user_ids(request.user)
    posts = (
        UserPost.objects.exclude(user_id__in=blocked_ids)
        .select_related("user", "user__userprofile")
        .prefetch_related("likes", "comments")
        .annotate(like_count=Count("likes"), comment_count=Count("comments"))
        .order_by("-like_count", "-comment_count", "-date")[:30]
    )
    posts = [p for p in posts if p.visibility == UserPost.VISIBILITY_PUBLIC or p.user_id == request.user.id]
    hashtags = {}
    for post in posts:
        for token in post.post.split():
            if token.startswith("#") and len(token) > 1:
                hashtags[token.lower()] = hashtags.get(token.lower(), 0) + 1

    trending_tags = sorted(hashtags.items(), key=lambda item: item[1], reverse=True)[:12]
    return render(request, "explore.html", {"posts": posts, "trending_tags": trending_tags})


@login_required(login_url="index")
def reels(request):
    blocked_ids = _blocked_user_ids(request.user)
    reels_posts = (
        UserPost.objects.exclude(user_id__in=blocked_ids)
        .exclude(video="")
        .exclude(video__isnull=True)
        .select_related("user", "user__userprofile")
        .prefetch_related("likes", "comments")
        .order_by("-date")
    )
    reels_posts = [p for p in reels_posts if p.visibility == UserPost.VISIBILITY_PUBLIC or p.user_id == request.user.id]
    return render(request, "reels.html", {"reels_posts": reels_posts})


@login_required(login_url="index")
def profile(request, username=None):
    target_user = request.user if username is None else get_object_or_404(User, username=username)
    blocked_ids = _blocked_user_ids(request.user)
    if target_user.id in blocked_ids:
        messages.error(request, "This profile is not available.")
        return redirect("home")

    friend_ids = _accepted_friend_ids(request.user)
    can_view_private = target_user == request.user or target_user.id in friend_ids
    posts = (
        UserPost.objects.filter(user=target_user)
        .select_related("user", "user__userprofile")
        .prefetch_related("likes", "comments", "comments__user")
        .order_by("-date")
    )
    if target_user != request.user:
        if target_user.userprofile.is_private and not can_view_private:
            posts = posts.none()
        else:
            posts = posts.exclude(visibility=UserPost.VISIBILITY_PRIVATE)

    friendship = None
    if target_user != request.user:
        friendship = _friendship_between(request.user, target_user)

    liked_post_ids = set(
        PostLike.objects.filter(user=request.user, post__in=posts).values_list("post_id", flat=True)
    )

    friend_count = len(_accepted_friend_ids(target_user))
    followers = Follow.objects.filter(following=target_user).count()
    following = Follow.objects.filter(follower=target_user).count()
    is_following = Follow.objects.filter(follower=request.user, following=target_user).exists()
    context = {
        "target_user": target_user,
        "posts": posts,
        "is_own_profile": target_user == request.user,
        "friendship": friendship,
        "liked_post_ids": liked_post_ids,
        "friend_count": friend_count,
        "followers": followers,
        "following": following,
        "is_following": is_following,
        "country_choices": COUNTRY_CHOICES,
    }
    return render(request, "profile.html", context)


@login_required(login_url="index")
def chat(request):
    user = request.user
    friend_ids = _accepted_friend_ids(user)
    peers = User.objects.filter(id__in=friend_ids).order_by("username")
    with_username = request.GET.get("with", "").strip()

    selected_user = None
    if with_username:
        selected_user = peers.filter(username=with_username).first()
    if selected_user is None and peers.exists():
        selected_user = peers.first()

    conversation = []
    if selected_user:
        conversation = Message.objects.filter(
            (Q(sender=user, recipient=selected_user) | Q(sender=selected_user, recipient=user))
        ).select_related("sender", "recipient").order_by("created_at")
        unread_ids = list(
            Message.objects.filter(sender=selected_user, recipient=user, is_read=False).values_list("id", flat=True)
        )
        Message.objects.filter(id__in=unread_ids).update(is_read=True, read_at=timezone.now())

        if unread_ids:
            channel_layer = get_channel_layer()
            room_name = f"direct_{min(user.id, selected_user.id)}_{max(user.id, selected_user.id)}"
            for mid in unread_ids:
                async_to_sync(channel_layer.group_send)(
                    room_name,
                    {
                        "type": "chat.receipt",
                        "message_id": mid,
                        "reader": user.username,
                    },
                )

    groups = ChatGroup.objects.filter(members__user=user).distinct().order_by("name")
    selected_user_last_seen = ""
    if selected_user:
        selected_user_last_seen = timezone.localtime(selected_user.userprofile.last_seen).strftime("%b %d, %H:%M")

    return render(
        request,
        "chat.html",
        {
            "peers": peers,
            "selected_user": selected_user,
            "conversation": conversation,
            "groups": groups,
            "selected_user_last_seen": selected_user_last_seen,
        },
    )


@login_required(login_url="index")
def send_message(request):
    if request.method != "POST":
        return redirect("chat")

    username = request.POST.get("username", "").strip()
    body = request.POST.get("body", "").strip()
    attachment = request.FILES.get("attachment")
    recipient = get_object_or_404(User, username=username)

    if recipient.id not in _accepted_friend_ids(request.user):
        messages.error(request, "You can only message accepted friends.")
        return redirect("chat")

    if body or attachment:
        msg = Message.objects.create(sender=request.user, recipient=recipient, body=body, attachment=attachment)
        room_name = f"direct_{min(request.user.id, recipient.id)}_{max(request.user.id, recipient.id)}"
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            room_name,
            {
                "type": "chat.message",
                "message": {
                    "id": msg.id,
                    "sender_id": request.user.id,
                    "sender": request.user.username,
                    "body": msg.body,
                    "created_at": msg.created_at.strftime("%b %d, %H:%M"),
                    "attachment": msg.attachment.url if msg.attachment else "",
                },
            },
        )
        _push_notification(
            recipient,
            request.user,
            Notification.TYPE_MESSAGE,
            f"@{request.user.username} sent you a message",
            f"/chat?with={request.user.username}",
        )

    return redirect(f"/chat?with={recipient.username}")


@login_required(login_url="index")
@require_POST
def create_group(request):
    name = request.POST.get("name", "").strip()
    usernames = request.POST.get("usernames", "").strip()
    if not name:
        messages.error(request, "Group name is required.")
        return redirect("chat")

    group = ChatGroup.objects.create(name=name, created_by=request.user)
    ChatGroupMember.objects.create(group=group, user=request.user)
    candidate_names = [x.strip() for x in usernames.split(",") if x.strip()]
    for uname in candidate_names:
        member = User.objects.filter(username=uname).first()
        if member and member != request.user:
            ChatGroupMember.objects.get_or_create(group=group, user=member)
    messages.success(request, "Group created.")
    return redirect(f"/chat/group/{group.id}")


@login_required(login_url="index")
def group_chat(request, group_id):
    group = get_object_or_404(ChatGroup, id=group_id)
    if not ChatGroupMember.objects.filter(group=group, user=request.user).exists():
        messages.error(request, "You are not a member of this group.")
        return redirect("chat")

    group_messages = group.messages.select_related("sender").order_by("created_at")
    groups = ChatGroup.objects.filter(members__user=request.user).distinct().order_by("name")
    group_member_usernames = list(group.members.select_related("user").values_list("user__username", flat=True))
    return render(
        request,
        "group_chat.html",
        {
            "group": group,
            "group_messages": group_messages,
            "groups": groups,
            "group_member_usernames": group_member_usernames,
            "group_member_usernames_json": json.dumps(group_member_usernames),
        },
    )


@login_required(login_url="index")
@require_POST
def send_group_message(request, group_id):
    group = get_object_or_404(ChatGroup, id=group_id)
    if not ChatGroupMember.objects.filter(group=group, user=request.user).exists():
        return redirect("chat")

    body = request.POST.get("body", "").strip()
    attachment = request.FILES.get("attachment")
    if body or attachment:
        msg = GroupMessage.objects.create(group=group, sender=request.user, body=body, attachment=attachment)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"group_{group.id}",
            {
                "type": "chat.message",
                "message": {
                    "id": msg.id,
                    "sender_id": request.user.id,
                    "sender": request.user.username,
                    "body": msg.body,
                    "created_at": msg.created_at.strftime("%b %d, %H:%M"),
                    "attachment": msg.attachment.url if msg.attachment else "",
                },
            },
        )

    return redirect(f"/chat/group/{group.id}")


def signout(request):
    logout(request)
    return redirect("index")


def register(request):
    if request.method != "POST":
        return redirect("index")

    username = request.POST.get("username", "").strip()
    pwd = request.POST.get("password", "")
    location = request.POST.get("location", "").strip()
    country = request.POST.get("country", "").strip()

    if len(username) < 3:
        messages.error(request, "Username must be at least 3 characters.")
        return redirect("index")
    if len(pwd) < 6:
        messages.error(request, "Password must be at least 6 characters.")
        return redirect("index")
    if User.objects.filter(username=username).exists():
        messages.error(request, "Username already exists.")
        return redirect("index")

    user = User.objects.create_user(username=username, password=pwd)
    user.userprofile.loc = location
    user.userprofile.country = country if country in dict(COUNTRY_CHOICES) else ""
    user.userprofile.save()
    messages.success(request, "Account created. Please log in.")
    return redirect("index")


@login_required(login_url="index")
def update_profile(request):
    if request.method == "POST":
        status = request.POST.get("status", "").strip()
        loc = request.POST.get("location", "").strip()
        country = request.POST.get("country", "").strip()
        education = request.POST.get("education", "").strip()
        work = request.POST.get("work", "").strip()
        is_private = request.POST.get("is_private") == "on"
        image = request.FILES.get("avatar")
        cover_image = request.FILES.get("cover")
        if status:
            request.user.userprofile.bio = status
        if loc:
            request.user.userprofile.loc = loc
        request.user.userprofile.country = country if country in dict(COUNTRY_CHOICES) else request.user.userprofile.country
        request.user.userprofile.education = education
        request.user.userprofile.work = work
        request.user.userprofile.is_private = is_private
        if image:
            request.user.userprofile.img = image
        if cover_image:
            request.user.userprofile.cover_img = cover_image
        request.user.userprofile.save()
        messages.success(request, "Profile updated.")
    return redirect("profile")


@login_required(login_url="index")
def create_post(request):
    if request.method == "POST":
        content = _sanitize_text(request.POST.get("content", "").strip())
        image = request.FILES.get("post_image")
        video = request.FILES.get("post_video")
        visibility = request.POST.get("visibility", UserPost.VISIBILITY_PUBLIC)
        if visibility not in {UserPost.VISIBILITY_PUBLIC, UserPost.VISIBILITY_FRIENDS, UserPost.VISIBILITY_PRIVATE}:
            visibility = UserPost.VISIBILITY_PUBLIC

        if content or image or video:
            UserPost.objects.create(user=request.user, post=content, image=image, video=video, visibility=visibility)
    return redirect("home")


@login_required(login_url="index")
def delete_post(request, post_id):
    post = get_object_or_404(UserPost, id=post_id, user=request.user)
    post.delete()
    return redirect("profile")


@login_required(login_url="index")
def toggle_like(request, post_id):
    post = get_object_or_404(UserPost, id=post_id)
    like = PostLike.objects.filter(user=request.user, post=post)
    if like.exists():
        like.delete()
    else:
        PostLike.objects.create(user=request.user, post=post)
        _push_notification(
            post.user,
            request.user,
            Notification.TYPE_LIKE,
            f"@{request.user.username} liked your post",
            "/home",
        )
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def add_comment(request, post_id):
    if request.method == "POST":
        post = get_object_or_404(UserPost, id=post_id)
        text = _sanitize_text(request.POST.get("comment", "").strip())
        if text:
            PostComment.objects.create(post=post, user=request.user, text=text)
            _push_notification(
                post.user,
                request.user,
                Notification.TYPE_COMMENT,
                f"@{request.user.username} commented on your post",
                "/home",
            )
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def send_friend_request(request, username):
    to_user = get_object_or_404(User, username=username)
    if to_user == request.user:
        return redirect(request.META.get("HTTP_REFERER", "home"))

    existing = _friendship_between(request.user, to_user)
    if existing is None:
        Friendship.objects.create(from_user=request.user, to_user=to_user, status=Friendship.STATUS_PENDING)
        _push_notification(
            to_user,
            request.user,
            Notification.TYPE_FRIEND,
            f"@{request.user.username} sent you a friend request",
            "/home",
        )
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def respond_friend_request(request, friendship_id, action):
    friendship = get_object_or_404(
        Friendship,
        id=friendship_id,
        to_user=request.user,
        status=Friendship.STATUS_PENDING,
    )

    if action == "accept":
        friendship.status = Friendship.STATUS_ACCEPTED
        friendship.save()
    else:
        friendship.delete()
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def unfriend(request, username):
    target_user = get_object_or_404(User, username=username)
    Friendship.objects.filter(
        (Q(from_user=request.user, to_user=target_user) | Q(from_user=target_user, to_user=request.user)),
        status=Friendship.STATUS_ACCEPTED,
    ).delete()
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def toggle_save_post(request, post_id):
    post = get_object_or_404(UserPost, id=post_id)
    save_qs = SavedPost.objects.filter(user=request.user, post=post)
    if save_qs.exists():
        save_qs.delete()
    else:
        SavedPost.objects.create(user=request.user, post=post)
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def saved_posts(request):
    posts = (
        UserPost.objects.filter(saves__user=request.user)
        .select_related("user", "user__userprofile")
        .prefetch_related("likes", "comments", "comments__user")
        .order_by("-date")
    )
    return render(request, "saved_posts.html", {"posts": posts})


@login_required(login_url="index")
@require_POST
def create_story(request):
    image = request.FILES.get("story_image")
    video = request.FILES.get("story_video")
    caption = request.POST.get("caption", "").strip()
    if image or video:
        Story.objects.create(
            user=request.user,
            image=image,
            video=video,
            caption=caption,
            expires_at=timezone.now() + timedelta(hours=24),
        )
    return redirect("home")


@login_required(login_url="index")
def notifications_view(request):
    notifications = Notification.objects.filter(recipient=request.user).select_related("actor").order_by("-created_at")
    return render(request, "notifications.html", {"notifications": notifications})


@login_required(login_url="index")
def mark_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def toggle_follow(request, username):
    target_user = get_object_or_404(User, username=username)
    if target_user == request.user:
        return redirect(request.META.get("HTTP_REFERER", "home"))

    follow_qs = Follow.objects.filter(follower=request.user, following=target_user)
    if follow_qs.exists():
        follow_qs.delete()
    else:
        Follow.objects.create(follower=request.user, following=target_user)
        _push_notification(
            target_user,
            request.user,
            Notification.TYPE_FOLLOW,
            f"@{request.user.username} started following you",
            f"/profile/{request.user.username}",
        )
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required(login_url="index")
def toggle_block(request, username):
    target_user = get_object_or_404(User, username=username)
    if target_user == request.user:
        return redirect(request.META.get("HTTP_REFERER", "home"))

    blocked_qs = BlockedUser.objects.filter(user=request.user, blocked_user=target_user)
    if blocked_qs.exists():
        blocked_qs.delete()
        messages.success(request, f"Unblocked @{target_user.username}.")
    else:
        BlockedUser.objects.create(user=request.user, blocked_user=target_user)
        Friendship.objects.filter(
            Q(from_user=request.user, to_user=target_user) | Q(from_user=target_user, to_user=request.user)
        ).delete()
        Follow.objects.filter(
            Q(follower=request.user, following=target_user) | Q(follower=target_user, following=request.user)
        ).delete()
        messages.success(request, f"Blocked @{target_user.username}.")
    return redirect("home")


@login_required(login_url="index")
def toggle_theme(request):
    profile = request.user.userprofile
    profile.theme = "dark" if profile.theme == "light" else "light"
    profile.save(update_fields=["theme"])
    return redirect(request.META.get("HTTP_REFERER", "home"))