"""
Serializers for ExpenseIQ API — matching the Node.js request/response format.
"""
from rest_framework import serializers
from .models import (
    Budget,
    Category,
    Chat,
    DeviceToken,
    Expense,
    Message,
    RecurringExpense,
    Report,
)


# ───── Category Serializer ─────
class CategorySerializer(serializers.ModelSerializer):
    monthlyBudget = serializers.DecimalField(
        source='monthly_budget', max_digits=12, decimal_places=2, required=False
    )
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'icon', 'color', 'monthlyBudget', 'createdAt', 'updatedAt']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['monthlyBudget'] = float(ret.get('monthlyBudget', 0) or 0)
        return ret


# ───── Recurring Expense Serializer ─────
class RecurringExpenseSerializer(serializers.ModelSerializer):
    categoryDetails = CategorySerializer(source='category', read_only=True)
    frequencyDisplay = serializers.SerializerMethodField()
    startDate = serializers.DateField(source='start_date')
    endDate = serializers.DateField(source='end_date', required=False, allow_null=True)
    nextDueDate = serializers.DateField(source='next_due_date', read_only=True)
    isActive = serializers.BooleanField(source='is_active', required=False)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = RecurringExpense
        fields = [
            'id', 'title', 'amount', 'category', 'categoryDetails',
            'frequency', 'frequencyDisplay', 'startDate', 'endDate',
            'nextDueDate', 'notes', 'isActive', 'createdAt', 'updatedAt',
        ]
        read_only_fields = ['id', 'createdAt', 'updatedAt', 'nextDueDate']

    def get_frequencyDisplay(self, obj):
        return obj.get_frequency_display()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Amount must be greater than 0.')
        return value

    def validate(self, data):
        request = self.context.get('request')
        if data.get('end_date') and data.get('start_date') and data['end_date'] <= data['start_date']:
            raise serializers.ValidationError({'endDate': 'End date must be after start date.'})
        if request and data.get('category'):
            if data['category'].user != request.user:
                raise serializers.ValidationError({'category': 'Category does not belong to this user.'})
        return data

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['amount'] = float(ret.get('amount', 0) or 0)
        ret['_id'] = str(ret['id'])
        return ret


# ───── Expense Serializer ─────
class ExpenseSerializer(serializers.ModelSerializer):
    paymentMethod = serializers.CharField(source='payment_method', required=False)
    receiptImage = serializers.ImageField(source='receipt_image', required=False, allow_null=True)
    expenseDate = serializers.DateTimeField(source='expense_date')
    isRecurring = serializers.BooleanField(source='is_recurring', required=False)
    recurringType = serializers.CharField(source='recurring_type', required=False, allow_null=True)
    recurringExpense = serializers.PrimaryKeyRelatedField(
        source='recurring_expense', allow_null=True, required=False,
        queryset=RecurringExpense.objects.all(),
    )
    recurringExpenseDetail = RecurringExpenseSerializer(
        source='recurring_expense', read_only=True, allow_null=True
    )
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id', 'title', 'amount', 'category', 'paymentMethod',
            'notes', 'receiptImage', 'expenseDate',
            'isRecurring', 'recurringType', 'recurringExpense', 'recurringExpenseDetail', 'tags',
            'createdAt', 'updatedAt',
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['amount'] = float(ret.get('amount', 0) or 0)
        # Add _id alias for frontend compatibility
        ret['_id'] = str(ret['id'])
        return ret


# ───── Budget Serializer ─────
class BudgetSerializer(serializers.ModelSerializer):
    totalMonthlyBudget = serializers.DecimalField(
        source='total_monthly_budget', max_digits=12, decimal_places=2
    )
    dailyBudget = serializers.DecimalField(
        source='daily_budget', max_digits=12, decimal_places=2, required=False, default=0
    )
    weeklyBudget = serializers.DecimalField(
        source='weekly_budget', max_digits=12, decimal_places=2, required=False, default=0
    )
    yearlyBudget = serializers.DecimalField(
        source='yearly_budget', max_digits=12, decimal_places=2, required=False, default=0
    )
    warningThreshold = serializers.IntegerField(source='warning_threshold', required=False)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Budget
        fields = [
            'id', 'month', 'year', 'dailyBudget', 'weeklyBudget', 
            'totalMonthlyBudget', 'yearlyBudget', 'warningThreshold', 
            'createdAt', 'updatedAt'
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['totalMonthlyBudget'] = float(ret.get('totalMonthlyBudget', 0) or 0)
        ret['dailyBudget'] = float(ret.get('dailyBudget', 0) or 0)
        ret['weeklyBudget'] = float(ret.get('weeklyBudget', 0) or 0)
        ret['yearlyBudget'] = float(ret.get('yearlyBudget', 0) or 0)
        ret['_id'] = str(ret['id'])
        return ret


# ───── Report Serializer ─────
class ReportSerializer(serializers.ModelSerializer):
    reportRange = serializers.SerializerMethodField()
    generatedFile = serializers.CharField(source='generated_file', read_only=True, allow_null=True)
    summary = serializers.SerializerMethodField()
    topCategory = serializers.CharField(source='top_category', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Report
        fields = [
            'id', 'type', 'reportRange', 'format', 'generatedFile',
            'summary', 'topCategory', 'createdAt', 'updatedAt',
        ]

    def get_reportRange(self, obj):
        return {
            'startDate': obj.start_date.isoformat() if obj.start_date else None,
            'endDate': obj.end_date.isoformat() if obj.end_date else None,
        }

    def get_summary(self, obj):
        return {
            'totalExpense': float(obj.total_expense),
            'totalIncome': float(obj.total_income),
            'netSavings': float(obj.net_savings),
            'topCategory': obj.top_category,
        }

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['_id'] = str(ret['id'])
        return ret


# ───── User Settings Serializer ─────
from .models import UserSettings

class UserSettingsSerializer(serializers.ModelSerializer):
    sidebarCollapsed = serializers.BooleanField(source='sidebar_collapsed', required=False)
    compactMode = serializers.BooleanField(source='compact_mode', required=False)
    currencySymbol = serializers.CharField(source='currency_symbol', required=False)
    dateFormat = serializers.CharField(source='date_format', required=False)
    numberFormat = serializers.CharField(source='number_format', required=False)
    budgetAlerts = serializers.BooleanField(source='budget_alerts', required=False)
    weeklyReport = serializers.BooleanField(source='weekly_report', required=False)
    recurringReminders = serializers.BooleanField(source='recurring_reminders', required=False)
    autoBackup = serializers.BooleanField(source='auto_backup', required=False)

    class Meta:
        model = UserSettings
        fields = [
            'theme', 'sidebarCollapsed', 'compactMode', 'animations',
            'currency', 'currencySymbol', 'dateFormat', 'numberFormat',
            'budgetAlerts', 'weeklyReport', 'recurringReminders', 'autoBackup'
        ]


class MessageSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    crudType = serializers.CharField(source='crud_type', required=False, default='none')
    crudRecord = serializers.JSONField(source='crud_record', required=False, allow_null=True)
    isDashboard = serializers.BooleanField(source='is_dashboard', required=False, default=False)

    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'crudType', 'crudRecord', 'isDashboard', 'createdAt']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['_id'] = str(ret['id'])
        return ret


class ChatSerializer(serializers.ModelSerializer):
    lastMessage = serializers.CharField(source='last_message', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Chat
        fields = ['id', 'title', 'lastMessage', 'messages', 'createdAt', 'updatedAt']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['_id'] = str(ret['id'])
        return ret


class DeviceTokenSerializer(serializers.ModelSerializer):
    """Registers a device token without ever returning its secret value."""

    class Meta:
        model = DeviceToken
        fields = ['id', 'token', 'platform', 'device_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'token': {'write_only': True, 'min_length': 20},
        }

    def validate_token(self, value):
        token = value.strip()
        if len(token) > 4096:
            raise serializers.ValidationError('Invalid device token.')
        return token

