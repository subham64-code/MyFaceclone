from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Post, Like, Comment, Profile


class AuthTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_landing_page_for_anonymous(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'MyFaceClone')

    def test_signup_creates_user_and_profile(self):
        response = self.client.post(reverse('signup'), {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'strongpass123',
        })
        self.assertRedirects(response, reverse('home'))
        user = User.objects.get(email='alice@example.com')
        self.assertEqual(user.first_name, 'Alice')
        self.assertTrue(hasattr(user, 'profile'))

    def test_login_valid_credentials(self):
        User.objects.create_user(username='bob', email='bob@example.com', password='pass1234')
        response = self.client.post(reverse('login'), {
            'email': 'bob@example.com',
            'password': 'pass1234',
        })
        self.assertRedirects(response, reverse('home'))

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login'), {
            'email': 'nobody@example.com',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password')

    def test_logout_redirects(self):
        User.objects.create_user(username='carol', email='carol@example.com', password='pass1234')
        self.client.login(username='carol', password='pass1234')
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('home'))


class PostTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='dave', email='dave@example.com', password='pass1234',
            first_name='Dave', last_name='Test'
        )
        self.client.login(username='dave', password='pass1234')

    def test_home_feed_for_authenticated_user(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What's on your mind")

    def test_create_post(self):
        response = self.client.post(reverse('create_post'), {
            'content': 'Test post content',
        })
        self.assertRedirects(response, reverse('home'))
        self.assertEqual(Post.objects.filter(author=self.user).count(), 1)
        self.assertEqual(Post.objects.first().content, 'Test post content')

    def test_like_post(self):
        post = Post.objects.create(author=self.user, content='Like test')
        response = self.client.post(
            reverse('toggle_like', args=[post.id]),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['liked'])
        self.assertEqual(data['count'], 1)

    def test_unlike_post(self):
        post = Post.objects.create(author=self.user, content='Unlike test')
        Like.objects.create(user=self.user, post=post)
        response = self.client.post(
            reverse('toggle_like', args=[post.id]),
            content_type='application/json',
        )
        data = response.json()
        self.assertFalse(data['liked'])
        self.assertEqual(data['count'], 0)

    def test_add_comment(self):
        import json
        post = Post.objects.create(author=self.user, content='Comment test')
        response = self.client.post(
            reverse('add_comment', args=[post.id]),
            data=json.dumps({'content': 'Nice post!'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['content'], 'Nice post!')
        self.assertEqual(Comment.objects.filter(post=post).count(), 1)


class ProfileTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='eve', email='eve@example.com', password='pass1234',
            first_name='Eve', last_name='Test'
        )
        self.client.login(username='eve', password='pass1234')

    def test_my_profile_page(self):
        response = self.client.get(reverse('my_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Eve')

    def test_user_profile_page(self):
        other = User.objects.create_user(
            username='frank', email='frank@example.com', password='pass1234',
            first_name='Frank', last_name='Other'
        )
        response = self.client.get(reverse('profile', args=['frank']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Frank')
