# MyFaceclone Production Architecture Blueprint

## 1) Folder Structure (Current + Target)

### Current repository (implemented now)
- MyFaceclone/
  - MyFaceclone/ (Django config)
  - social/ (models, views, urls)
  - templates/
  - static/
  - Dockerfile
  - docker-compose.yml
  - k8s/
  - .github/workflows/ci.yml

### Target microservices structure (recommended for scale)
- apps/
  - web-next/ (Next.js + Tailwind + TypeScript)
  - api-gateway/ (BFF/API gateway)
  - auth-service/
  - user-service/
  - feed-service/
  - post-service/
  - chat-service/
  - notification-service/
  - moderation-service/
- infra/
  - k8s/
  - terraform/
  - helm/
- packages/
  - shared-types/
  - ui-kit/

## 2) Database Schema (ER explanation)

### Implemented in Django app
- User (auth user)
- UserProfile (1:1 with User): bio, loc, img, cover_img, education, work, is_private, theme
- UserPost (N:1 User): post, image, video, visibility, date
- PostLike (N:1 User, N:1 UserPost)
- PostComment (N:1 User, N:1 UserPost)
- Friendship (from_user -> to_user, pending/accepted)
- Follow (follower -> following)
- Message (sender -> recipient)
- SavedPost (user -> post)
- Story (user -> media, expires_at)
- BlockedUser (user -> blocked_user)
- Notification (recipient, actor, type, text, link, is_read)

### Index recommendations
- UserPost: (user_id, -date), (visibility, -date)
- Message: (sender_id, recipient_id, -created_at)
- Notification: (recipient_id, is_read, -created_at)
- Follow: unique(follower_id, following_id)
- Friendship: unique(from_user_id, to_user_id)

## 3) REST API Endpoints (existing patterns)

- Auth
  - POST / (login)
  - POST /register
  - GET /logout
- Feed & posts
  - GET /home
  - POST /addpost
  - GET /post/{post_id}/delete
  - GET /post/{post_id}/like
  - POST /post/{post_id}/comment
  - GET /post/{post_id}/save
  - GET /saved
- Profiles
  - GET /profile
  - GET /profile/{username}
  - POST /update
  - GET /theme/toggle
- Social graph
  - GET /friend/{username}/send
  - GET /friend/request/{friendship_id}/{action}
  - GET /friend/{username}/unfriend
  - GET /follow/{username}/toggle
  - GET /block/{username}/toggle
- Stories
  - POST /story/create
- Chat
  - GET /chat
  - POST /chat/send
- Notifications
  - GET /notifications
  - GET /notifications/read

## 4) WebSocket Events (target design)

- chat:typing:start { roomId, userId }
- chat:typing:stop { roomId, userId }
- chat:message { roomId, message }
- chat:read { roomId, messageId, userId }
- notification:new { userId, payload }
- presence:update { userId, status }

Transport options:
- Django Channels + Redis channel layer
- Socket.IO service behind API gateway

## 5) Authentication Flow Diagram

1. User submits credentials / OAuth token.
2. Auth service validates identity.
3. Issues short-lived access JWT + rotating refresh token.
4. API gateway verifies JWT (public keys / shared secret).
5. Service-level authorization checks ownership/visibility.
6. Refresh endpoint rotates refresh token and revokes old token.

## 6) Feed Algorithm Logic

Current implemented score (simple ML-like weighted ranking):
- score = 2 * likes + 3 * comments + recency_boost
- recency_boost decays over time from first 24h
- filter by privacy, friend graph, and blocked users

Scale-up evolution:
- Feature store: author affinity, dwell time, hide/report signal
- Candidate generation + ranker model + re-ranker
- Cache top-N per user in Redis sorted sets

## 7) Sample Code Snippets

### Auth (Django view pattern)
```python
user = authenticate(username=username, password=password)
if user:
    login(request, user)
```

### Create Post
```python
UserPost.objects.create(
    user=request.user,
    post=content,
    image=image,
    video=video,
    visibility=visibility,
)
```

### Chat Send + Notification
```python
Message.objects.create(sender=request.user, recipient=recipient, body=body)
Notification.objects.create(
    recipient=recipient,
    actor=request.user,
    type="message",
    text=f"@{request.user.username} sent you a message",
)
```

## 8) Deployment Steps (Docker + CI/CD + K8s)

1. Build image
   - docker build -t myfaceclone:latest .
2. Run locally
   - docker compose up --build
3. CI pipeline
   - .github/workflows/ci.yml runs check, tests, and image build
4. Deploy to Kubernetes
   - kubectl apply -f k8s/redis.yaml
   - kubectl apply -f k8s/deployment.yaml

## 9) Performance Optimization Techniques

- Redis caching for feed pages and hot post counters
- DB indexes on timeline and graph edges
- Select related/prefetch related to avoid N+1 queries
- Asynchronous workers for notifications/media processing
- CDN fronting S3 media
- Pagination/infinite scroll for posts/comments

## 10) Scaling Strategy (Millions of Users)

- Split monolith into microservices by domain boundaries
- API gateway with rate limiting and circuit breakers
- Event bus (Kafka/RabbitMQ) for fan-out notifications and feed updates
- Read replicas for PostgreSQL + partitioning for large tables
- Redis cluster for feed cache/session/state
- Stateless app pods with autoscaling (HPA)
- Observability stack: structured logs, metrics, tracing, SLO alerts

## Security Checklist

- JWT + refresh token rotation
- OAuth (Google) for social login
- CORS allow-list and CSRF protection
- Password hashing (Django default PBKDF2/Argon2 option)
- Content moderation pipeline for toxic comments
- Encryption at rest for object storage and DB

## Notes

- This repository now includes a production-ready foundation and deployment assets.
- For full Next.js frontend and dedicated microservices, use the target structure above as the next migration phase.
