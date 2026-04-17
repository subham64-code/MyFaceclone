from django.contrib import admin
from social.models import (
	BlockedUser,
	ChatGroup,
	ChatGroupMember,
	Follow,
		GroupMessage,
	Friendship,
	Message,
	Notification,
	PostComment,
	PostLike,
	SavedPost,
	Story,
	UserPost,
	UserProfile,
)
#register your model here
admin.site.register(UserProfile)
admin.site.register(UserPost)
admin.site.register(Friendship)
admin.site.register(PostLike)
admin.site.register(PostComment)
admin.site.register(Message)
admin.site.register(Follow)
admin.site.register(Story)
admin.site.register(SavedPost)
admin.site.register(BlockedUser)
admin.site.register(Notification)
admin.site.register(ChatGroup)
admin.site.register(ChatGroupMember)
admin.site.register(GroupMessage)

