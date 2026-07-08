"""
ai_view.py — ExpenseIQ AI Assistant
=====================================
POST /api/v1/ai/assistant

Supports: text, audio (filename), image (filename)
Flow:
  1. Build live user context from DB
  2. Send to Groq LLM with system prompt
  3. Parse JSON intent from AI response
  4. Execute CRUD via serializers
  5. Return message + crud_record to frontend
"""

import os
import re
import json
import logging
from datetime import datetime

from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
import requests

from ..utils import ApiResponse
from ..models import Expense, Budget, Category, AIChatMessage
from ..serializers import (
    ExpenseSerializer,
    BudgetSerializer,
    CategorySerializer,
)
from ..authentication import CookieJWTAuthentication

logger = logging.getLogger(__name__)

# ── Config (override via environment variables in production) ────────────────
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")          # Never hardcode in prod!
GROQ_MODEL        = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL      = os.environ.get("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_TEMPERATURE  = float(os.environ.get("GROQ_TEMPERATURE", "0.3"))   # Low = consistent JSON
GROQ_MAX_TOKENS   = int(os.environ.get("GROQ_MAX_TOKENS", "600"))


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(value, default: float = 0.0) -> float:
    """
    Safely convert any value to float.
    Handles: None, int, float, "₹500", "15,000.50", "about 200", etc.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").replace("₹", "").replace("$", "").replace("€", "").strip()
    match = re.search(r"[-+]?\d+\.?\d*", s)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return default


def _get_non_none(keys: list, src: dict):
    """Return first non-None value from src matching any key in keys list."""
    for k in keys:
        v = src.get(k)
        if v is not None:
            return v
    return None


def _parse_month(value) -> int | None:
    """Parse month from int, 'January', or 'Jan' → 1-12. Returns None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        pass
    for fmt in ("%B", "%b"):
        try:
            return datetime.strptime(str(value).strip(), fmt).month
        except ValueError:
            pass
    return None


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` markdown wrappers AI sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# USER CONTEXT BUILDER — injects live DB snapshot into AI system prompt
# ─────────────────────────────────────────────────────────────────────────────

def _build_user_context(user) -> str:
    """
    Returns a compact, token-efficient financial snapshot for the AI prompt.
    Format: space-separated [KEY:value] blocks.
    """
    now = datetime.now()
    m, y = now.month, now.year
    days_passed = now.day
    days_in_month = 30  # approximate

    parts = [f"[USER:{user.username}|DATE:{now.strftime('%d-%b-%Y')}|DAY:{days_passed}/30]"]

    # ── Recent 15 expenses ────────────────────────────────────────────
    expenses = Expense.objects.filter(user=user).order_by("-expense_date")[:15]
    if expenses.exists():
        rows = "|".join(
            f"{e.expense_date.strftime('%d%b') if e.expense_date else '?'},"
            f"{e.title[:18]},₹{e.amount},{e.category},{e.payment_method}"
            for e in expenses
        )
        parts.append(f"[EXPENSES(date,title,amt,cat,pay):{rows}]")
    else:
        parts.append("[EXPENSES:none]")

    # ── This month summary ────────────────────────────────────────────
    me = Expense.objects.filter(user=user, expense_date__month=m, expense_date__year=y)
    month_total = me.aggregate(t=Sum("amount"))["t"] or 0
    cats = me.values("category").annotate(t=Sum("amount")).order_by("-t")
    cat_str = ",".join(f"{c['category']}:₹{c['t']:.0f}" for c in cats) or "none"
    daily_avg = float(month_total) / days_passed if days_passed else 0
    projected = daily_avg * days_in_month
    parts.append(
        f"[THIS_MONTH:{now.strftime('%b%Y')}|spent:₹{month_total:.0f}|txns:{me.count()}"
        f"|daily_avg:₹{daily_avg:.0f}|projected:₹{projected:.0f}|by_cat:{cat_str}]"
    )

    # ── Last month comparison ─────────────────────────────────────────
    lm, ly = (m - 1, y) if m > 1 else (12, y - 1)
    lm_total = (
        Expense.objects.filter(user=user, expense_date__month=lm, expense_date__year=ly)
        .aggregate(t=Sum("amount"))["t"]
        or 0
    )
    change_pct = (
        ((float(month_total) - float(lm_total)) / float(lm_total) * 100) if lm_total else 0
    )
    trend_dir = "up" if change_pct > 0 else ("down" if change_pct < 0 else "same")
    parts.append(f"[LAST_MONTH:₹{lm_total:.0f}|vs_now:{trend_dir}{abs(change_pct):.0f}%]")

    # ── 3-month trend ─────────────────────────────────────────────────
    trend = []
    for delta in [2, 1, 0]:
        tm = (m - delta - 1) % 12 + 1
        ty = y - ((m - delta - 1) // 12)
        t_total = (
            Expense.objects.filter(user=user, expense_date__month=tm, expense_date__year=ty)
            .aggregate(t=Sum("amount"))["t"]
            or 0
        )
        trend.append(f"{datetime(ty, tm, 1).strftime('%b')}:₹{t_total:.0f}")
    parts.append(f"[3M_TREND:{','.join(trend)}]")

    # ── Recurring expenses ────────────────────────────────────────────
    recurring = Expense.objects.filter(user=user, is_recurring=True).order_by("-expense_date")[:8]
    if recurring.exists():
        rec_str = ",".join(
            f"{e.title[:15]}:₹{e.amount}({e.recurring_type or 'monthly'})" for e in recurring
        )
        parts.append(f"[RECURRING:{rec_str}]")

    # ── Budget health ─────────────────────────────────────────────────
    try:
        b = Budget.objects.filter(user=user, month=m, year=y).first()
        if b and b.total_monthly_budget:
            rem = float(b.total_monthly_budget) - float(month_total)
            pct = float(month_total) / float(b.total_monthly_budget) * 100
            days_left = days_in_month - days_passed
            safe_daily = rem / days_left if days_left > 0 else 0
            status = "OK" if pct < 80 else ("WARNING" if pct < 100 else "OVER")
            parts.append(
                f"[BUDGET:₹{b.total_monthly_budget:.0f}|used:{pct:.0f}%|left:₹{rem:.0f}"
                f"|safe_daily:₹{safe_daily:.0f}|status:{status}]"
            )
    except Exception as exc:
        logger.warning(f"Budget context error: {exc}")

    # ── Category budget usage ─────────────────────────────────────────
    try:
        cat_budgets = Category.objects.filter(user=user, monthly_budget__gt=0)
        if cat_budgets.exists():
            cb_parts = []
            for cb in cat_budgets:
                spent = me.filter(category=cb.name).aggregate(t=Sum("amount"))["t"] or 0
                cb_pct = (float(spent) / float(cb.monthly_budget) * 100) if cb.monthly_budget else 0
                cb_parts.append(f"{cb.name}:{cb_pct:.0f}%")
            parts.append(f"[CAT_BUDGETS(cat,used%):{','.join(cb_parts)}]")
    except Exception as exc:
        logger.warning(f"Category budget context error: {exc}")

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# CRUD EXECUTOR
# ─────────────────────────────────────────────────────────────────────────────

def _execute_crud(user, intent: str, data: dict) -> dict:
    """
    Executes DB operations based on AI-parsed intent + data.
    Always returns: {"message": str, "crud_type": str, "crud_record": any, "ok": bool}
    crud_type values: "created" | "updated" | "deleted" | "none"
    """

    def ok(msg, crud_type, record=None):
        return {"message": msg, "crud_type": crud_type, "crud_record": record, "ok": True}

    def err(msg):
        return {"message": msg, "crud_type": "none", "crud_record": None, "ok": False}

    try:

        # ── ADD EXPENSE ───────────────────────────────────────────────
        if intent == "add_expense":
            raw_date = data.get("expense_date")
            try:
                exp_date = datetime.fromisoformat(raw_date) if raw_date else datetime.now()
            except Exception:
                exp_date = datetime.now()

            payload = {
                "title":         data.get("title", "Expense"),
                "amount":        _to_float(data.get("amount"), 0),
                "category":      data.get("category", "Other"),
                "paymentMethod": data.get("payment_method", "Cash"),
                "notes":         data.get("notes", ""),
                "expenseDate":   exp_date.isoformat(),
                "isRecurring":   data.get("is_recurring", False),
                "recurringType": data.get("recurring_type"),
            }
            ser = ExpenseSerializer(data=payload)
            if not ser.is_valid():
                return err(f"❌ Validation failed: {ser.errors}")
            e = ser.save(user=user)
            record = {
                "id": e.id, "_id": str(e.id),
                "title": e.title, "amount": float(e.amount),
                "category": e.category, "payment_method": e.payment_method,
                "expense_date": e.expense_date.isoformat(),
            }
            return ok(f"✅ Added **{e.title}** — ₹{e.amount} ({e.category})", "created", record)

        # ── EDIT EXPENSE ──────────────────────────────────────────────
        elif intent == "edit_expense":
            search = data.get("search", "").strip()
            fields = data.get("fields", {})
            if not search:
                return err("❌ Provide a search keyword to find the expense.")
            qs = Expense.objects.filter(
                user=user, title__icontains=search
            ).order_by("-expense_date")
            if not qs.exists():
                return err(f"❌ No expense matching '{search}' found.")
            e = qs.first()
            # Map snake_case AI keys → serializer camelCase keys
            field_map = {
                "payment_method": "paymentMethod",
                "expense_date":   "expenseDate",
                "is_recurring":   "isRecurring",
                "recurring_type": "recurringType",
            }
            payload = {field_map.get(k, k): v for k, v in fields.items()}
            ser = ExpenseSerializer(e, data=payload, partial=True)
            if not ser.is_valid():
                return err(f"❌ Validation failed: {ser.errors}")
            e = ser.save()
            record = {
                "id": e.id, "_id": str(e.id),
                "title": e.title, "amount": float(e.amount),
                "category": e.category, "payment_method": e.payment_method,
                "expense_date": e.expense_date.isoformat(),
            }
            return ok(f"✏️ Updated **{e.title}** — ₹{e.amount} ({e.category})", "updated", record)

        # ── DELETE EXPENSE ────────────────────────────────────────────
        elif intent == "del_expense":
            search = data.get("search", "").strip()
            if not search:
                return err("❌ Provide a search keyword to delete the expense.")
            qs = Expense.objects.filter(
                user=user, title__icontains=search
            ).order_by("-expense_date")
            if not qs.exists():
                return err(f"❌ No expense matching '{search}' found.")
            e = qs.first()
            name, amt = e.title, e.amount
            e.delete()
            return ok(f"🗑️ Deleted **{name}** (₹{amt})", "deleted", {"id": e.id})

        # ── LIST EXPENSES ─────────────────────────────────────────────
        elif intent == "list_expenses":
            limit          = min(int(data.get("limit", 10)), 50)   # max 50
            category_filter = data.get("category")
            month_filter   = _parse_month(data.get("month"))
            year_filter    = data.get("year")

            qs = Expense.objects.filter(user=user).order_by("-expense_date")
            if category_filter:
                qs = qs.filter(category__iexact=category_filter)
            if month_filter:
                qs = qs.filter(expense_date__month=month_filter)
            if year_filter:
                qs = qs.filter(expense_date__year=int(year_filter))

            expenses = qs[:limit]
            if not expenses:
                return ok("ℹ️ No expenses found matching your criteria.", "none")

            total = 0
            lines, records = [], []
            for e in expenses:
                records.append(ExpenseSerializer(e).data)
                date_str = e.expense_date.strftime("%d %b") if e.expense_date else "?"
                lines.append(
                    f"• {date_str} — **{e.title}** ₹{e.amount} ({e.category}, {e.payment_method})"
                )
                total += float(e.amount)
            msg = f"📋 **Expenses** (showing {len(lines)}, total ₹{total:.0f}):\n" + "\n".join(lines)
            return ok(msg, "none", records)

        # ── SET / UPSERT BUDGET ───────────────────────────────────────
        elif intent == "set_budget":
            now   = datetime.now()
            month = _parse_month(_get_non_none(["month", "month_val"], data)) or now.month
            year  = int(_get_non_none(["year", "year_val"], data) or now.year)

            existing = Budget.objects.filter(user=user, month=month, year=year).first()

            total_val   = _get_non_none(["total", "monthly", "monthly_budget", "totalMonthlyBudget"], data)
            weekly_val  = _get_non_none(["weekly", "weekly_budget", "weeklyBudget"], data)
            daily_val   = _get_non_none(["daily", "daily_budget", "dailyBudget"], data)
            yearly_val  = _get_non_none(["yearly", "yearly_budget", "yearlyBudget"], data)
            warning_val = _get_non_none(["warning_threshold", "warningThreshold", "threshold"], data)

            total = _to_float(total_val) if total_val is not None else (existing.total_monthly_budget if existing else 0.0)
            weekly = _to_float(weekly_val) if weekly_val is not None else (existing.weekly_budget if existing else 0.0)
            daily = _to_float(daily_val) if daily_val is not None else (existing.daily_budget if existing else 0.0)
            yearly = _to_float(yearly_val) if yearly_val is not None else (existing.yearly_budget if existing else 0.0)
            threshold = int(_to_float(warning_val)) if warning_val is not None else (existing.warning_threshold if existing else 80)

            b, created = Budget.objects.update_or_create(
                user=user, month=month, year=year,
                defaults={
                    "total_monthly_budget": total,
                    "weekly_budget": weekly,
                    "daily_budget": daily,
                    "yearly_budget": yearly,
                    "warning_threshold": threshold,
                }
            )

            month_label = datetime(b.year, b.month, 1).strftime("%B %Y")
            verb        = "Created" if created else "Updated"
            record = {
                "type": "budget", "month": month_label,
                "total": float(b.total_monthly_budget),
                "weekly": float(b.weekly_budget),
                "daily":  float(b.daily_budget),
            }
            return ok(
                f"💰 {verb} budget for **{month_label}** — "
                f"₹{b.total_monthly_budget:.0f}/month | ₹{b.weekly_budget:.0f}/week | ₹{b.daily_budget:.0f}/day",
                "updated" if not created else "created",
                record,
            )

        # ── DELETE BUDGET ─────────────────────────────────────────────
        elif intent == "del_budget":
            now   = datetime.now()
            month = _parse_month(_get_non_none(["month", "month_val"], data)) or now.month
            year  = int(_get_non_none(["year", "year_val"], data) or now.year)
            try:
                b = Budget.objects.get(user=user, month=month, year=year)
            except Budget.DoesNotExist:
                label = datetime(year, month, 1).strftime("%B %Y")
                return err(f"❌ No budget found for {label}.")
            label = datetime(b.year, b.month, 1).strftime("%B %Y")
            b.delete()
            return ok(f"🗑️ Deleted budget for **{label}**", "deleted", {"type": "budget"})

        # ── LIST BUDGETS ──────────────────────────────────────────────
        elif intent == "list_budgets":
            budgets = Budget.objects.filter(user=user).order_by("-year", "-month")
            if not budgets.exists():
                return ok("ℹ️ You haven't set any budgets yet.", "none")
            lines, records = [], []
            for b in budgets:
                label = datetime(b.year, b.month, 1).strftime("%B %Y")
                records.append(BudgetSerializer(b).data)
                lines.append(
                    f"• **{label}** — ₹{b.total_monthly_budget:.0f}/month | "
                    f"₹{b.weekly_budget:.0f}/week | ₹{b.daily_budget:.0f}/day"
                )
            return ok("💰 **Your Budgets:**\n" + "\n".join(lines), "none", records)

        # ── ADD CATEGORY ──────────────────────────────────────────────
        elif intent == "add_category":
            name = data.get("name", "").strip()
            if not name:
                return err("❌ Category name is required.")
            if Category.objects.filter(user=user, name__iexact=name).exists():
                return ok(f"ℹ️ Category **{name}** already exists.", "none")

            # Rotate through a palette so each new category gets a distinct default color
            _CATEGORY_PALETTE = [
                "#10b981",  # emerald
                "#3b82f6",  # blue
                "#f97316",  # orange
                "#8b5cf6",  # violet
                "#ec4899",  # pink
                "#14b8a6",  # teal
                "#f59e0b",  # amber
                "#ef4444",  # red
                "#06b6d4",  # cyan
                "#84cc16",  # lime
                "#a855f7",  # purple
                "#fb923c",  # light orange
            ]
            existing_count = Category.objects.filter(user=user).count()
            default_color  = _CATEGORY_PALETTE[existing_count % len(_CATEGORY_PALETTE)]

            payload = {
                "name":          name,
                "monthlyBudget": _to_float(data.get("monthly_budget"), 0),
                "icon":          data.get("icon") or "ph-package",
                "color":         data.get("color") or default_color,
            }
            ser = CategorySerializer(data=payload)
            if not ser.is_valid():
                return err(f"❌ Validation failed: {ser.errors}")
            c = ser.save(user=user)
            return ok(f"✅ Created category **{c.name}** (₹{c.monthly_budget:.0f}/month)", "created", CategorySerializer(c).data)

        # ── EDIT CATEGORY ─────────────────────────────────────────────
        elif intent == "edit_category":
            name = data.get("name", "").strip()
            fields = data.get("fields", {})
            if not name:
                return err("❌ Category name is required.")
            try:
                c = Category.objects.get(user=user, name__iexact=name)
            except Category.DoesNotExist:
                return err(f"❌ Category '{name}' not found.")
            field_map = {"monthly_budget": "monthlyBudget"}
            payload = {field_map.get(k, k): v for k, v in fields.items()}
            ser = CategorySerializer(c, data=payload, partial=True)
            if not ser.is_valid():
                return err(f"❌ Validation failed: {ser.errors}")
            c = ser.save()
            return ok(
                f"✏️ Updated category **{c.name}** (budget ₹{c.monthly_budget:.0f}/month)",
                "updated",
                CategorySerializer(c).data
            )

        # ── DELETE CATEGORY ───────────────────────────────────────────
        elif intent == "del_category":
            name = data.get("name", "").strip()
            if not name:
                return err("❌ Category name is required.")
            try:
                c = Category.objects.get(user=user, name__iexact=name)
            except Category.DoesNotExist:
                return err(f"❌ Category '{name}' not found.")
            c.delete()
            return ok(f"🗑️ Deleted category **{name}**", "deleted", {"type": "category"})

        # ── LIST CATEGORIES ───────────────────────────────────────────
        elif intent == "list_categories":
            categories = Category.objects.filter(user=user).order_by("name")
            if not categories.exists():
                return ok("ℹ️ You haven't created any categories yet.", "none")
            lines, records = [], []
            for c in categories:
                records.append(CategorySerializer(c).data)
                budget_str = f" (₹{c.monthly_budget:.0f}/month)" if c.monthly_budget > 0 else ""
                lines.append(f"• {c.icon} **{c.name}**{budget_str}")
            return ok("📂 **Your Categories:**\n" + "\n".join(lines), "none", records)

        # ── CHANGE THEME ──────────────────────────────────────────────
        elif intent == "change_theme":
            theme = data.get("theme", "dark").lower()
            if theme not in ["light", "dark"]:
                theme = "dark"
            
            # Save it to the user's settings if possible
            from ..models import UserSettings
            try:
                us, _ = UserSettings.objects.get_or_create(user=user)
                if us.theme != theme:
                    us.theme = theme
                    us.save()
            except Exception as e:
                logger.warning(f"Failed to update theme in DB: {e}")

            return ok(f"🎨 Theme changed to **{theme}** mode.", "change_theme", {"theme": theme})

    except Exception as exc:
        logger.exception(f"CRUD execution error for intent={intent}: {exc}")
        return err(f"❌ Operation failed: {exc}")

    # No matching intent (shouldn't reach here for CRUD intents)
    return {"message": "", "crud_type": "none", "crud_record": None, "ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You are ExpenseIQ, a personal finance AI with full CRUD access to the user's data.
ALWAYS respond in valid JSON only — no markdown, no extra text, no explanation outside JSON.

Response format:
{{"intent": "...", "message": "...", "data": {{...}}}}

Available intents:
  none            — question/answer, no DB change
  add_expense     — data: {{title, amount, category, payment_method, expense_date(ISO), notes, is_recurring?, recurring_type?}}
  edit_expense    — data: {{search (title keyword), fields: {{title?, amount?, category?, payment_method?, notes?}}}}
  del_expense     — data: {{search (title keyword)}}
  list_expenses   — data: {{limit?(default 10, max 50), category?, month?, year?}}
  set_budget      — data: {{total?, weekly?, daily?, yearly?, month?, year?}} — include ONLY changed fields
  del_budget      — data: {{month?, year?}}
  list_budgets    — data: {{}}
  add_category    — data: {{name, monthly_budget?, icon?, color?}}
  edit_category   — data: {{name, fields: {{monthly_budget?, icon?, color?}}}}
  del_category    — data: {{name}}
  list_categories — data: {{}}
  change_theme    — data: {{theme: "light" | "dark"}}

Rules:
- message: 1-3 sentences, friendly. Use **bold** for amounts and names.
- For set_budget: include a short 2-3 line category allocation tip based on user's past spend.
- For none intent: answer from user data below. Be concise.
- Dates: always ISO format (2025-06-15T00:00:00).
- payment_method choices: Cash, UPI, Credit Card, Debit Card, Bank Transfer, Auto Pay, Other

USER FINANCIAL DATA:
{user_context}
"""


# ─────────────────────────────────────────────────────────────────────────────
# ALL CRUD INTENT NAMES (used to route AI response to _execute_crud)
# ─────────────────────────────────────────────────────────────────────────────

CRUD_INTENTS = {
    "add_expense", "edit_expense", "del_expense", "list_expenses",
    "set_budget",  "del_budget",   "list_budgets",
    "add_category","edit_category","del_category","list_categories",
    "change_theme",
}


# ─────────────────────────────────────────────────────────────────────────────
# AI ASSISTANT VIEW
# ─────────────────────────────────────────────────────────────────────────────

class AIAssistantView(APIView):
    """
    POST /api/v1/ai/assistant
    GET /api/v1/ai/assistant
    DELETE /api/v1/ai/assistant
    """

    authentication_classes = [CookieJWTAuthentication]
    permission_classes     = []  # unauthenticated allowed (demo fallback to first user)
    parser_classes         = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            from django.contrib.auth.models import User
            user = User.objects.first()
            if not user:
                return ApiResponse.error("No user found. Please log in.", 401)
        
        db_messages = AIChatMessage.objects.filter(user=user).order_by('created_at')
        history = []
        for msg in db_messages:
            history.append({
                "role": "user",
                "parts": msg.prompt
            })
            history.append({
                "role": "model",
                "parts": msg.response,
                "crudType": msg.crud_type,
                "crudRecord": msg.crud_record,
                "isDashboard": msg.is_dashboard
            })
        return ApiResponse.success(data={"history": history}, message="History retrieved successfully")

    def delete(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            from django.contrib.auth.models import User
            user = User.objects.first()
            if not user:
                return ApiResponse.error("No user found. Please log in.", 401)
        
        AIChatMessage.objects.filter(user=user).delete()
        return ApiResponse.success(message="History cleared successfully")

    def post(self, request):
        # ── 1. Validate inputs ────────────────────────────────────────
        text       = request.data.get("text", "").strip()
        audio_file = request.FILES.get("audio")
        image_file = request.FILES.get("image")

        if not text and not audio_file and not image_file:
            return ApiResponse.error("Provide 'text', 'audio', or 'image' input.", 400)

        if not GROQ_API_KEY:
            logger.error("GROQ_API_KEY not set in environment.")
            return ApiResponse.error("AI service not configured. Set GROQ_API_KEY.", 503)

        # ── 2. Resolve user (demo fallback) ──────────────────────────
        user = request.user
        if not user or not user.is_authenticated:
            from django.contrib.auth.models import User
            user = User.objects.first()
            if not user:
                return ApiResponse.error("No user found. Please log in.", 401)

        # ── 3. Handle Special Dashboard Command locally ──────────────────
        if text == '📊 Show me my dashboard':
            ai_message = "📊 Here's your financial overview for this month:"
            AIChatMessage.objects.create(
                user=user,
                prompt=text,
                response=ai_message,
                crud_type='none',
                crud_record=None,
                is_dashboard=True
            )
            return ApiResponse.success(
                data={
                    "message":     ai_message,
                    "crud_type":   "none",
                    "crud_record": None,
                    "action":      None,
                },
                message="AI responded successfully",
            )

        # ── 4. Parse conversation history from Database ──────────────────
        db_messages = AIChatMessage.objects.filter(user=user).order_by('created_at')

        # ── 5. Build live user context from DB ────────────────────────
        try:
            user_context = _build_user_context(user)
        except Exception as exc:
            logger.warning(f"Failed to build user context: {exc}")
            user_context = "No financial data available."

        # ── 6. Build messages for Groq ────────────────────────────────
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(user_context=user_context)
        messages = [{"role": "system", "content": system_prompt}]

        # Append conversation history (multi-turn support)
        for msg in db_messages:
            if msg.prompt.strip():
                messages.append({"role": "user", "content": msg.prompt})
            if msg.response.strip():
                messages.append({"role": "assistant", "content": msg.response})

        # Build current user prompt
        prompt = text or "Analyze the uploaded media for expense-related information."
        if audio_file:
            prompt += f"\n[Audio file: {audio_file.name}]"
        if image_file:
            prompt += f"\n[Image file: {image_file.name}]"
        messages.append({"role": "user", "content": prompt})

        # ── 7. Call Groq API ──────────────────────────────────────────
        logger.info(f"Groq call: model={GROQ_MODEL} user={user.username}")
        try:
            resp = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model":       GROQ_MODEL,
                    "messages":    messages,
                    "temperature": GROQ_TEMPERATURE,
                    "max_tokens":  GROQ_MAX_TOKENS,
                },
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error("Groq API timeout")
            return ApiResponse.error("AI service timed out. Please try again.", 503)
        except requests.exceptions.HTTPError as e:
            logger.error(f"Groq HTTP error: {e.response.status_code} — {e.response.text}")
            return ApiResponse.error(f"AI service error: {e.response.status_code}", 503)
        except Exception as exc:
            logger.exception(f"Groq call failed: {exc}")
            return ApiResponse.error(f"AI service unavailable: {exc}", 503)

        # ── 8. Parse AI JSON response ─────────────────────────────────
        raw_content = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if isinstance(raw_content, list):
            raw_content = " ".join(str(p.get("text", "")) for p in raw_content if isinstance(p, dict))

        ai_message  = raw_content or "Sorry, I couldn't process that."
        intent      = "none"
        ai_data     = {}
        crud_type   = "none"
        crud_record = None

        try:
            cleaned = _strip_json_fences(raw_content)
            parsed  = json.loads(cleaned)
            if isinstance(parsed, dict):
                intent     = parsed.get("intent", "none")
                ai_message = parsed.get("message", ai_message)
                ai_data    = parsed.get("data") or {}
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(f"AI response not JSON: {exc} — content: {raw_content[:200]}")

        # ── 9. Execute CRUD if needed ─────────────────────────────────
        if intent in CRUD_INTENTS:
            result      = _execute_crud(user, intent, ai_data)
            ai_message  = result["message"] or ai_message
            crud_type   = result["crud_type"]
            crud_record = result.get("crud_record")

        # ── 10. Save to Database ──────────────────────────────────────
        AIChatMessage.objects.create(
            user=user,
            prompt=prompt,
            response=ai_message,
            crud_type=crud_type,
            crud_record=crud_record,
            is_dashboard=(intent == "none" and "financial overview" in ai_message)
        )

        # ── 11. Return response ───────────────────────────────────────
        return ApiResponse.success(
            data={
                "message":     ai_message,
                "crud_type":   crud_type,
                "crud_record": crud_record,
                "action":      None,
            },
            message="AI responded successfully",
        )