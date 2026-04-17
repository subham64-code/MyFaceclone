document.addEventListener("DOMContentLoaded", () => {
	const chatThread = document.querySelector("[data-chat-thread]");
	if (chatThread) {
		chatThread.scrollTop = chatThread.scrollHeight;
	}

	const cards = document.querySelectorAll(".card, .story-item, .bubble");
	if ("IntersectionObserver" in window) {
		const observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (entry.isIntersecting) {
						entry.target.style.transform = "translateY(0)";
						entry.target.style.opacity = "1";
						observer.unobserve(entry.target);
					}
				});
			},
			{ threshold: 0.1 }
		);

		cards.forEach((card) => {
			card.style.transform = "translateY(8px)";
			card.style.opacity = "0";
			card.style.transition = "opacity 380ms ease, transform 380ms ease";
			observer.observe(card);
		});
	}

	const alerts = document.querySelectorAll(".alert");
	alerts.forEach((alertEl, index) => {
		setTimeout(() => {
			alertEl.style.transition = "opacity 400ms ease, transform 400ms ease";
			alertEl.style.opacity = "0";
			alertEl.style.transform = "translateY(-6px)";
			setTimeout(() => alertEl.remove(), 420);
		}, 3500 + index * 250);
	});

	const reels = document.querySelectorAll(".reel-video");
	if ("IntersectionObserver" in window && reels.length > 0) {
		const reelObserver = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					const video = entry.target;
					if (entry.isIntersecting && entry.intersectionRatio > 0.65) {
						video.play().catch(() => {});
					} else {
						video.pause();
					}
				});
			},
			{ threshold: [0.3, 0.65, 0.95] }
		);

		reels.forEach((video) => reelObserver.observe(video));
	}
});
