from django.db import models
from django.contrib.auth.models import User
import pycountry

from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.

COUNTRY_CHOICES = sorted(
    [(country.alpha_2, country.name) for country in pycountry.countries],
    key=lambda item: item[1],
)

class UserProfile (models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    loc= models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=2, choices=COUNTRY_CHOICES, blank=True)
    bio = models.TextField(max_length=300, blank=True)
    img = models.ImageField(upload_to='pics', default='avatar.jpg')
    cover_img = models.ImageField(upload_to='covers', default='cover.jpg')
    education = models.CharField(max_length=120, blank=True)
    work = models.CharField(max_length=120, blank=True)
    is_private = models.BooleanField(default=False)
    theme = models.CharField(max_length=20, default='light')
    last_seen = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.user.username+' profile'
    
class UserPost(models.Model):
    VISIBILITY_PUBLIC = "public"
    VISIBILITY_FRIENDS = "friends"
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PUBLIC, "Public"),
        (VISIBILITY_FRIENDS, "Friends"),
        (VISIBILITY_PRIVATE, "Only me"),
    ]

    user = models.ForeignKey (User,on_delete=models.CASCADE)
    post = models.TextField(max_length=300, blank=False)
    image = models.ImageField(upload_to='posts', blank=True, null=True)
    video = models.FileField(upload_to='post_videos', blank=True, null=True)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default=VISIBILITY_PUBLIC)
    date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.user.username+' post'


class Friendship(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
    ]

    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_friendships",
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_friendships",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="unique_friend_direction"),
        ]

    def __str__(self):
        return f"{self.from_user.username} -> {self.to_user.username} ({self.status})"


class PostLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(UserPost, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "post"], name="unique_post_like"),
        ]


class PostComment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(UserPost, on_delete=models.CASCADE, related_name="comments")
    text = models.CharField(max_length=280)
    created_at = models.DateTimeField(auto_now_add=True)


class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_messages")
    body = models.TextField(max_length=1000, blank=True)
    attachment = models.FileField(upload_to="chat_media", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    is_delivered = models.BooleanField(default=True)
    read_at = models.DateTimeField(blank=True, null=True)


class ChatGroup(models.Model):
    name = models.CharField(max_length=120)
    avatar = models.ImageField(upload_to="group_avatars", blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_groups")
    created_at = models.DateTimeField(auto_now_add=True)


class ChatGroupMember(models.Model):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="unique_group_member"),
        ]


class GroupMessage(models.Model):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_messages")
    body = models.TextField(max_length=1000, blank=True)
    attachment = models.FileField(upload_to="group_chat_media", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name="following_set")
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follower_set")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="unique_follow"),
        ]


class Story(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stories")
    image = models.ImageField(upload_to="stories", blank=True, null=True)
    video = models.FileField(upload_to="story_videos", blank=True, null=True)
    caption = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


class SavedPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_posts")
    post = models.ForeignKey(UserPost, on_delete=models.CASCADE, related_name="saves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "post"], name="unique_saved_post"),
        ]


class BlockedUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocked_users")
    blocked_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocked_by_users")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "blocked_user"], name="unique_user_block"),
        ]


class Notification(models.Model):
    TYPE_LIKE = "like"
    TYPE_COMMENT = "comment"
    TYPE_FOLLOW = "follow"
    TYPE_FRIEND = "friend"
    TYPE_MESSAGE = "message"
    TYPE_CHOICES = [
        (TYPE_LIKE, "Like"),
        (TYPE_COMMENT, "Comment"),
        (TYPE_FOLLOW, "Follow"),
        (TYPE_FRIEND, "Friend request"),
        (TYPE_MESSAGE, "Message"),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="actor_notifications")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    text = models.CharField(max_length=220)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=250, blank=True)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save,sender=User)

def save_user_profile(sender, instance, **kwargs):
    instance.userprofile.save()