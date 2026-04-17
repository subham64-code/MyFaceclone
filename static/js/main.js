/* MyFaceClone – main.js */

document.addEventListener('DOMContentLoaded', function () {
    /* ---- Like buttons ---- */
    document.querySelectorAll('.like-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var postId = btn.dataset.postId;
            var csrfToken = btn.dataset.csrf;

            fetch('/post/' + postId + '/like/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var countEl = document.getElementById('like-count-' + postId);
                if (countEl) { countEl.textContent = data.count; }

                var icon = btn.querySelector('i');
                var label = btn.querySelector('span');

                if (data.liked) {
                    btn.classList.add('liked');
                    if (icon) {
                        icon.classList.remove('far');
                        icon.classList.add('fas');
                    }
                    if (label) { label.textContent = 'Liked'; }
                } else {
                    btn.classList.remove('liked');
                    if (icon) {
                        icon.classList.remove('fas');
                        icon.classList.add('far');
                    }
                    if (label) { label.textContent = 'Like'; }
                }
            })
            .catch(function (err) { console.error('Like error:', err); });
        });
    });

    /* ---- Comment toggle ---- */
    document.querySelectorAll('.comment-toggle-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var postId = btn.dataset.postId;
            var section = document.getElementById('comments-' + postId);
            if (section) {
                section.classList.toggle('hidden');
                if (!section.classList.contains('hidden')) {
                    var input = section.querySelector('.comment-input');
                    if (input) { input.focus(); }
                }
            }
        });
    });

    /* ---- Comment submit on Enter ---- */
    document.querySelectorAll('.comment-input').forEach(function (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                var content = input.value.trim();
                if (!content) { return; }

                var postId = input.dataset.postId;
                var csrfToken = input.dataset.csrf;

                fetch('/post/' + postId + '/comment/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'Content-Type': 'application/json',
                    },
                    credentials: 'same-origin',
                    body: JSON.stringify({ content: content }),
                })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.error) { return; }

                    var list = document.getElementById('comments-list-' + postId);
                    if (list) {
                        var div = document.createElement('div');
                        div.className = 'comment';
                        div.innerHTML =
                            '<span class="comment-avatar default-avatar" style="width:32px;height:32px;font-size:12px;">' +
                            (data.author ? data.author.charAt(0).toUpperCase() : '?') +
                            '</span>' +
                            '<div class="comment-bubble">' +
                            '<span class="comment-author">' + escapeHtml(data.author) + '</span>' +
                            '<p class="comment-content">' + escapeHtml(data.content) + '</p>' +
                            '</div>';
                        list.appendChild(div);
                    }

                    // Update comment count
                    var countEl = document.getElementById('comment-count-' + postId);
                    if (countEl) {
                        countEl.textContent = parseInt(countEl.textContent || '0', 10) + 1;
                    }

                    input.value = '';
                })
                .catch(function (err) { console.error('Comment error:', err); });
            }
        });
    });

    /* ---- Post modal ---- */
    var postModal = document.getElementById('post-modal');
    var textarea = document.getElementById('post-textarea');
    var submitBtn = document.getElementById('post-submit-btn');

    function openPostModal() {
        if (postModal) {
            postModal.classList.remove('hidden');
            if (textarea) { textarea.focus(); }
        }
    }

    function closePostModal() {
        if (postModal) { postModal.classList.add('hidden'); }
    }

    ['open-post-modal', 'open-post-modal-photo', 'open-post-modal-feeling'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) { el.addEventListener('click', openPostModal); }
    });

    var closeBtn = document.getElementById('close-post-modal');
    if (closeBtn) { closeBtn.addEventListener('click', closePostModal); }

    // Enable submit button when textarea has content or image selected
    if (textarea && submitBtn) {
        textarea.addEventListener('input', function () {
            submitBtn.disabled = textarea.value.trim() === '' &&
                !document.getElementById('post-image-input')?.files.length;
        });
    }

    // Image preview in post modal
    var imageInput = document.getElementById('post-image-input');
    var previewWrap = document.getElementById('image-preview-wrap');
    var previewImg = document.getElementById('image-preview');
    var removeImageBtn = document.getElementById('remove-image');

    if (imageInput) {
        imageInput.addEventListener('change', function () {
            var file = imageInput.files[0];
            if (file && previewImg && previewWrap) {
                var reader = new FileReader();
                reader.onload = function (e) {
                    previewImg.src = e.target.result;
                    previewWrap.classList.remove('hidden');
                    if (submitBtn) { submitBtn.disabled = false; }
                };
                reader.readAsDataURL(file);
            }
        });
    }

    if (removeImageBtn && imageInput && previewWrap) {
        removeImageBtn.addEventListener('click', function () {
            imageInput.value = '';
            previewWrap.classList.add('hidden');
            if (previewImg) { previewImg.src = ''; }
            if (submitBtn && textarea) {
                submitBtn.disabled = textarea.value.trim() === '';
            }
        });
    }

    // Close modal on overlay click
    if (postModal) {
        postModal.addEventListener('click', function (e) {
            if (e.target === postModal) { closePostModal(); }
        });
    }

    /* ---- Close modals on Escape ---- */
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            if (postModal) { postModal.classList.add('hidden'); }
            var signupModal = document.getElementById('signup-modal');
            if (signupModal) { signupModal.classList.add('hidden'); }
        }
    });
});

/* ---- Utility: HTML escape ---- */
function escapeHtml(str) {
    if (!str) { return ''; }
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
