"""
Views for ExpenseIQ API — Recurring Expense endpoints.
Implements CRUD using DRF ViewSets with authentication, pagination,
filtering, ordering, and search.
"""
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from ..models import RecurringExpense
from ..serializers import RecurringExpenseSerializer
from ..utils import ApiResponse, get_pagination_params


class RecurringExpenseFilter(filters.FilterSet):
    """FilterSet for RecurringExpense with frequency and active status."""

    isActive = filters.BooleanFilter(field_name='is_active')
    frequency = filters.ChoiceFilter(choices=RecurringExpense.FREQUENCY_CHOICES)

    class Meta:
        model = RecurringExpense
        fields = ['is_active', 'frequency']


class RecurringExpenseViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for RecurringExpense.
    
    Provides list, create, retrieve, update, partial_update, destroy actions.
    Only returns recurring expenses belonging to the authenticated user.
    Pagination: page/limit query params.
    Filters: isActive, frequency.
    Search: title, category__name.
    Order: amount, next_due_date, created_at.
    """
    serializer_class = RecurringExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = RecurringExpenseFilter
    search_fields = ['title', 'category__name']
    ordering_fields = ['amount', 'next_due_date', 'created_at']
    ordering = '-next_due_date'

    def get_queryset(self):
        return RecurringExpense.objects.filter(
            user=self.request.user
        ).select_related('category')

    def list(self, request, *args, **kwargs):
        page, limit = get_pagination_params(request.query_params)

        queryset = self.filter_queryset(self.get_queryset())
        total = queryset.count()

        offset = (page - 1) * limit
        page_queryset = queryset[offset:offset + limit]

        serializer = self.get_serializer(page_queryset, many=True)
        return ApiResponse.paginated(serializer.data, page, limit, total)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            print("RE_CREATE FAILED. Data:", request.data)
            print("RE_CREATE ERRORS:", serializer.errors)
            return ApiResponse.error('Validation failed', status.HTTP_400_BAD_REQUEST, serializer.errors)


        next_due_date = serializer.validated_data.get('start_date')
        re = serializer.save(user=request.user, next_due_date=next_due_date)
        return ApiResponse.created(
            self.get_serializer(re).data,
            message='Recurring expense created successfully',
        )

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Exception:
            return ApiResponse.error('Recurring expense not found', status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return ApiResponse.success(serializer.data)

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Exception:
            return ApiResponse.error('Recurring expense not found', status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            instance, data=request.data, partial=False, context={'request': request}
        )
        if not serializer.is_valid():
            return ApiResponse.error('Validation failed', status.HTTP_400_BAD_REQUEST, serializer.errors)
        re = serializer.save()
        return ApiResponse.success(
            self.get_serializer(re).data,
            message='Recurring expense updated successfully',
        )

    def partial_update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Exception:
            return ApiResponse.error('Recurring expense not found', status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            instance, data=request.data, partial=True, context={'request': request}
        )
        if not serializer.is_valid():
            return ApiResponse.error('Validation failed', status.HTTP_400_BAD_REQUEST, serializer.errors)
        re = serializer.save()
        return ApiResponse.success(
            self.get_serializer(re).data,
            message='Recurring expense updated successfully',
        )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Exception:
            return ApiResponse.error('Recurring expense not found', status.HTTP_404_NOT_FOUND)
        instance.delete()
        return ApiResponse.success(message='Recurring expense deleted successfully')

    from rest_framework.decorators import action
    from rest_framework.response import Response

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle the is_active status of a recurring expense (pause/resume)."""
        try:
            instance = self.get_object()
        except Exception:
            return ApiResponse.error('Recurring expense not found', status.HTTP_404_NOT_FOUND)

        instance.is_active = not instance.is_active
        instance.save(update_fields=['is_active'])
        status_text = 'resumed' if instance.is_active else 'paused'
        return ApiResponse.success(
            self.get_serializer(instance).data,
            message=f'Recurring expense {status_text} successfully',
        )
