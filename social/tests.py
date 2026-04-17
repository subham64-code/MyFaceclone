from django.contrib.auth.models import User
from django.test import TestCase


class CorePagesTests(TestCase):
	def setUp(self):
		self.password = "Pass12345!"
		self.user = User.objects.create_user(username="tester", password=self.password)
		self.client.login(username=self.user.username, password=self.password)

	def test_index_shows_country_selector(self):
		self.client.logout()
		response = self.client.get("/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="country"')
		self.assertContains(response, "Choose your country")

	def test_core_authenticated_pages_load(self):
		for path in ["/home", "/explore", "/reels", "/saved", "/notifications", "/profile", "/chat"]:
			with self.subTest(path=path):
				response = self.client.get(path)
				self.assertEqual(response.status_code, 200)

	def test_profile_page_for_current_user_loads(self):
		response = self.client.get(f"/profile/{self.user.username}")
		self.assertEqual(response.status_code, 200)
