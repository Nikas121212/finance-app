import pandas as pd
from datetime import date, timedelta
from db import get_conn

MANDATORY_MONTHLY = {
    "Аренда места": 22000,
    "Коммуналка": 5000,
    "Продукты": 12000,
}
MANDATORY_TOTAL = sum(MANDATORY_MONTHLY.values())


def load_transactions():
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date", conn)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load_goals():
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM goals ORDER BY priority", conn)


def load_debts():
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM debts ORDER BY closed, date_created", conn)


def load_templates():
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM recurring_templates", conn)


def get_balance():
    df = load_transactions()
    if df.empty:
        return 0.0
    income = df.loc[df.kind == "income", "amount"].sum()
    expense = df.loc[df.kind == "expense", "amount"].sum()
    return income - expense


def get_available_balance():
    """Balance minus money already earmarked (saved) for goals."""
    bal = get_balance()
    goals = load_goals()
    reserved = goals["saved_amount"].sum() if not goals.empty else 0
    return bal - reserved


def get_weekly_income_series(weeks=12):
    df = load_transactions()
    income = df[df.kind == "income"] if not df.empty else pd.DataFrame(columns=["date", "amount"])
    end = pd.Timestamp(date.today())
    start = end - pd.Timedelta(weeks=weeks)
    idx = pd.date_range(start=start, end=end, freq="W-MON")
    if income.empty:
        series = pd.Series(0.0, index=idx)
    else:
        income = income.set_index("date").sort_index()
        series = income["amount"].resample("W-MON").sum()
        series = series.reindex(idx, fill_value=0.0)
    return series


def get_expense_breakdown(days=30):
    df = load_transactions()
    if df.empty:
        return pd.DataFrame(columns=["category", "amount"])
    cutoff = pd.Timestamp(date.today()) - pd.Timedelta(days=days)
    expenses = df[(df.kind == "expense") & (df.date >= cutoff)]
    if expenses.empty:
        return pd.DataFrame(columns=["category", "amount"])
    return expenses.groupby("category")["amount"].sum().reset_index().sort_values("amount", ascending=False)


def get_average_weekly_income(weeks=8):
    series = get_weekly_income_series(weeks=weeks)
    nonzero = series[series > 0]
    if nonzero.empty:
        return 0.0
    return nonzero.mean()


def forecast_month_end():
    today = date.today()
    days_in_month = (date(today.year + (today.month == 12), (today.month % 12) + 1, 1) - timedelta(days=1)).day
    days_left = days_in_month - today.day

    df = load_transactions()
    month_start = pd.Timestamp(today.year, today.month, 1)
    this_month = df[df.date >= month_start] if not df.empty else pd.DataFrame(columns=["kind", "amount"])
    income_so_far = this_month.loc[this_month.kind == "income", "amount"].sum() if not this_month.empty else 0
    expense_so_far = this_month.loc[this_month.kind == "expense", "amount"].sum() if not this_month.empty else 0

    avg_weekly = get_average_weekly_income()
    daily_rate = avg_weekly / 7 if avg_weekly else 0
    projected_additional_income = daily_rate * days_left

    mandatory_left = max(MANDATORY_TOTAL - expense_so_far, 0)

    projected_balance_change = (income_so_far + projected_additional_income) - (expense_so_far + mandatory_left)
    return {
        "income_so_far": income_so_far,
        "expense_so_far": expense_so_far,
        "projected_additional_income": projected_additional_income,
        "mandatory_left": mandatory_left,
        "projected_month_net": projected_balance_change,
        "days_left": days_left,
    }


def get_allocation_order():
    """Returns ordered list of (type, id, name, remaining_amount) by priority: debts (i_owe) first, then goals."""
    order = []
    debts = load_debts()
    unpaid_debts = debts[(debts.direction == "i_owe") & (debts.closed == 0)]
    for _, d in unpaid_debts.iterrows():
        order.append({"type": "debt", "id": d.id, "name": f"Долг: {d.counterparty}", "remaining": d.amount})

    goals = load_goals()
    for _, g in goals.iterrows():
        remaining = g.target_amount - g.saved_amount
        if remaining > 0:
            order.append({"type": "goal", "id": g.id, "name": g["name"], "remaining": remaining})
    return order


def forecast_goal_dates():
    avg_weekly = get_average_weekly_income()
    disposable_weekly = max(avg_weekly - (MANDATORY_TOTAL / 4.33), 0)
    order = get_allocation_order()

    results = []
    cumulative_weeks = 0.0
    for item in order:
        if disposable_weekly <= 0:
            results.append({**item, "eta_weeks": None})
            continue
        weeks_needed = item["remaining"] / disposable_weekly
        cumulative_weeks += weeks_needed
        eta_date = date.today() + timedelta(weeks=cumulative_weeks)
        results.append({**item, "eta_weeks": round(cumulative_weeks, 1), "eta_date": eta_date})
    return results, disposable_weekly


def dead_season_warning():
    avg_weekly = get_average_weekly_income()
    weekly_mandatory = MANDATORY_TOTAL / 4.33
    goals = load_goals()
    cushion = goals[goals["name"].str.contains("мёртвый сезон", case=False)]
    cushion_saved = cushion["saved_amount"].iloc[0] if not cushion.empty else 0
    cushion_target = cushion["target_amount"].iloc[0] if not cushion.empty else 150000

    weeks_of_cushion = cushion_saved / weekly_mandatory if weekly_mandatory else 0

    warnings = []
    if avg_weekly < weekly_mandatory:
        warnings.append(
            f"Средний недельный доход ({avg_weekly:,.0f} ₽) ниже обязательных недельных трат "
            f"({weekly_mandatory:,.0f} ₽) — расходуете резерв быстрее, чем пополняете."
        )
    if weeks_of_cushion < 4 and cushion_saved < cushion_target:
        warnings.append(
            f"Подушка покрывает примерно {weeks_of_cushion:.1f} нед. обязательных трат — "
            f"цель минимум 4-8 недель на случай простоя."
        )
    return warnings
