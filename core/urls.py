from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('post/create/', views.create_post, name='create_post'),
    path('post/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('post/<int:post_id>/comment/', views.add_comment, name='add_comment'),
    path('profile/', views.profile_view, name='my_profile'),
    path('profile/<str:username>/', views.profile_view, name='profile'),
    path('friend-request/<int:user_id>/send/', views.send_friend_request, name='send_friend_request'),
    path('friend-request/<int:request_id>/respond/', views.respond_friend_request, name='respond_friend_request'),
]
