from django.urls import path
from .views.chat_views import (
    ChatListCreateView,
    ChatDetailView,
    MessageListCreateView,
)

urlpatterns = [
    path('', ChatListCreateView.as_view(), name='chat-list-create'),
    path('<int:pk>/', ChatDetailView.as_view(), name='chat-detail'),
    path('<int:chat_pk>/messages/', MessageListCreateView.as_view(), name='message-list-create'),
]
