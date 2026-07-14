"""
Django models for ExpenseIQ — migrated from Mongoose schemas.
Using SQLite as the database backend.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User


class Category(models.Model):
    """Expense category with optional monthly budget."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, default=1, related_name='categories')
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, default='ph-package')
    color = models.CharField(max_length=20, default='#10b981')
    monthly_budget = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_user_category')
        ]

    def save(self, *args, **kwargs):
        if not self.user_id or not User.objects.filter(id=self.user_id).exists():
            user = User.objects.first()
            if not user:
                user = User.objects.create_user('default_user', 'default@example.com', 'defaultpassword123')
            self.user = user
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.icon} {self.name}"


class RecurringExpense(models.Model):
    """Recurring expense template that generates Expense records automatically."""

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, default=1, related_name='recurring_expenses')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='recurring_expenses')
    title = models.CharField(max_length=255, db_index=True)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField(db_index=True)
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-next_due_date']
        indexes = [
            models.Index(fields=['is_active', 'next_due_date']),
            models.Index(fields=['user', 'is_active']),
        ]

    def save(self, *args, **kwargs):
        if not self.user_id or not User.objects.filter(id=self.user_id).exists():
            user = User.objects.first()
            if not user:
                user = User.objects.create_user('default_user', 'default@example.com', 'defaultpassword123')
            self.user = user
        if not self.next_due_date:
            self.next_due_date = self.start_date
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_frequency_display()}) — ${self.amount}"


class Expense(models.Model):
    """Individual expense transaction."""

    PAYMENT_METHOD_CHOICES = [
        ('Credit Card', 'Credit Card'),
        ('Debit Card', 'Debit Card'),
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('UPI', 'UPI'),
        ('Auto Pay', 'Auto Pay'),
        ('Other', 'Other'),
    ]

    RECURRING_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, default=1, related_name='expenses')
    title = models.CharField(max_length=255, db_index=True)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    category = models.CharField(max_length=100, db_index=True)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default='Cash'
    )
    notes = models.TextField(blank=True, default='')
    receipt_image = models.ImageField(upload_to='receipts/', blank=True, null=True)
    expense_date = models.DateTimeField(db_index=True)
    is_recurring = models.BooleanField(default=False)
    recurring_type = models.CharField(
        max_length=10, choices=RECURRING_TYPE_CHOICES, blank=True, null=True
    )
    recurring_expense = models.ForeignKey(
        RecurringExpense, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='generated_expenses'
    )
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date']
        indexes = [
            models.Index(fields=['-expense_date', 'category']),
            models.Index(fields=['-expense_date', '-amount']),
            models.Index(fields=['category', '-expense_date']),
            models.Index(fields=['recurring_expense', 'expense_date']),
        ]

    def save(self, *args, **kwargs):
        if not self.user_id or not User.objects.filter(id=self.user_id).exists():
            user = User.objects.first()
            if not user:
                user = User.objects.create_user('default_user', 'default@example.com', 'defaultpassword123')
            self.user = user

        # Automatic RecurringExpense template management
        if self.is_recurring:
            freq = self.recurring_type or 'monthly'
            from .utils import calculate_next_due_date
            from django.utils import timezone
            
            # If not yet linked to a recurring template, look for a match or create one
            if not self.recurring_expense:
                # Find Category
                cat_obj = Category.objects.filter(user=self.user, name=self.category).first()
                if not cat_obj:
                    cat_obj = Category.objects.filter(user=self.user).first()
                if not cat_obj:
                    cat_obj = Category.objects.create(user=self.user, name=self.category or 'Other', icon='ph-package', color='#6366f1')
                
                # Check for an existing matching active template to avoid duplicates
                re = RecurringExpense.objects.filter(
                    user=self.user,
                    title=self.title,
                    amount=self.amount,
                    frequency=freq,
                    is_active=True
                ).first()
                
                if not re:
                    start_val = self.expense_date.date() if self.expense_date else timezone.now().date()
                    re = RecurringExpense.objects.create(
                        user=self.user,
                        category=cat_obj,
                        title=self.title,
                        amount=self.amount,
                        frequency=freq,
                        start_date=start_val,
                        next_due_date=calculate_next_due_date(start_val, freq),
                        is_active=True,
                        notes=self.notes or ''
                    )
                self.recurring_expense = re
            else:
                # Sync properties to the existing template
                re = self.recurring_expense
                cat_obj = Category.objects.filter(user=self.user, name=self.category).first()
                if cat_obj:
                    re.category = cat_obj
                re.title = self.title
                re.amount = self.amount
                re.frequency = freq
                re.notes = self.notes or ''
                re.save()
        else:
            # If this is an update, check if they explicitly toggled recurring off
            if self.pk:
                original = Expense.objects.filter(pk=self.pk).first()
                if original and original.is_recurring and self.recurring_expense:
                    re = self.recurring_expense
                    re.is_active = False
                    re.save()
                    self.recurring_expense = None

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Delete associated recurring template if it exists
        if self.is_recurring and self.recurring_expense:
            re = self.recurring_expense
            re.delete()
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.title} — ${self.amount}"



class Budget(models.Model):
    """Monthly budget settings."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, default=1, related_name='budgets')
    month = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    year = models.IntegerField()
    total_monthly_budget = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    daily_budget = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    weekly_budget = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    yearly_budget = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    warning_threshold = models.IntegerField(
        default=80,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'year', 'month']
        ordering = ['-year', '-month']

    def save(self, *args, **kwargs):
        if not self.user_id or not User.objects.filter(id=self.user_id).exists():
            user = User.objects.first()
            if not user:
                user = User.objects.create_user('default_user', 'default@example.com', 'defaultpassword123')
            self.user = user
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Budget {self.month}/{self.year} — ${self.total_monthly_budget}"


class Report(models.Model):
    """Generated report metadata and summary."""

    REPORT_TYPE_CHOICES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom'),
        ('financial_summary', 'Financial Summary'),
    ]
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('csv', 'CSV'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, default=1, related_name='reports')
    type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    format = models.CharField(max_length=5, choices=FORMAT_CHOICES, default='pdf')
    generated_file = models.CharField(max_length=500, blank=True, null=True)
    total_expense = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_savings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    top_category = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['type', '-created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.user_id or not User.objects.filter(id=self.user_id).exists():
            user = User.objects.first()
            if not user:
                user = User.objects.create_user('default_user', 'default@example.com', 'defaultpassword123')
            self.user = user
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.type} report ({self.start_date.date()} – {self.end_date.date()})"


class UserSettings(models.Model):
    """User preferences — replaces all localStorage storage."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings')

    # Appearance
    theme = models.CharField(max_length=10, default='dark', choices=[('dark', 'Dark'), ('light', 'Light')])
    sidebar_collapsed = models.BooleanField(default=False)
    compact_mode = models.BooleanField(default=False)
    animations = models.BooleanField(default=True)

    # Currency & Regional
    currency = models.CharField(max_length=10, default='USD')
    currency_symbol = models.CharField(max_length=5, default='$')
    date_format = models.CharField(max_length=20, default='YYYY-MM-DD')
    number_format = models.CharField(max_length=20, default='1,000.00')

    # Notifications
    budget_alerts = models.BooleanField(default=True)
    weekly_report = models.BooleanField(default=True)
    recurring_reminders = models.BooleanField(default=True)
    auto_backup = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'user settings'

    def __str__(self):
        return f"Settings for {self.user.username}"


class DeviceToken(models.Model):
    """An FCM registration token for one signed-in user's device or browser."""

    PLATFORM_CHOICES = [
        ('web', 'Web'),
        ('android', 'Android'),
        ('ios', 'iOS'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.TextField()
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='web')
    device_name = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_seen_at']

    def save(self, *args, **kwargs):
        from hashlib import sha256

        self.token_hash = sha256(self.token.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.platform} device for {self.user.username}"


class NotificationEvent(models.Model):
    """Records deduplicated notification events sent to a user."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_events')
    event_type = models.CharField(max_length=50)
    deduplication_key = models.CharField(max_length=150)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'event_type', 'deduplication_key'],
                name='unique_user_notification_event',
            )
        ]


class AIChatMessage(models.Model):
    """Stores user prompt and AI response history."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    prompt = models.TextField()
    response = models.TextField()
    crud_type = models.CharField(max_length=20, default='none')
    crud_record = models.JSONField(blank=True, null=True)
    is_dashboard = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Chat for {self.user.username} at {self.created_at}"


class Chat(models.Model):
    """A chat conversation session."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats')
    title = models.CharField(max_length=255, default='New Chat')
    last_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Chat: {self.title} for {self.user.username}"


class Message(models.Model):
    """An individual message in a chat conversation."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    crud_type = models.CharField(max_length=20, default='none')
    crud_record = models.JSONField(blank=True, null=True)
    is_dashboard = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role} message in Chat {self.chat.id} at {self.created_at}"
